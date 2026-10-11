using AppointmentIntegration.Api.Models;
using AppointmentIntegration.Api.Tests.Support;
using Microsoft.EntityFrameworkCore;

namespace AppointmentIntegration.Api.Tests.Unit;

public class AppointmentPaymentServiceTests
{
    [Fact]
    public async Task NoShowCannotStartNewPaymentsOrSubmitReceipts()
    {
        using var f = new PaymentFixture(); await f.Select("BankTransfer");
        (await f.Db.Appointments.SingleAsync()).Status = AppointmentStatus.NoShow; await f.Db.SaveChangesAsync();
        await Assert.ThrowsAsync<InvalidOperationException>(() => f.Select("Cash"));
        await Assert.ThrowsAsync<InvalidOperationException>(() => f.Payments.UploadReceiptAsync(PaymentFixture.Patient, 1, PaymentFixture.Receipt()));
        Assert.Empty(f.Storage.Files);
    }

    [Fact]
    public async Task NoShowCannotStartAnOnlinePayment()
    {
        using var f = new PaymentFixture(); await f.Select("PaymentGateway");
        (await f.Db.Appointments.SingleAsync()).Status = AppointmentStatus.NoShow; await f.Db.SaveChangesAsync();
        await Assert.ThrowsAsync<InvalidOperationException>(() => f.Start()); Assert.Empty(f.Db.AppointmentOnlinePaymentAttempts);
    }
    [Theory]
    [InlineData("Cash", AppointmentPaymentStatus.Pending)]
    [InlineData("BankTransfer", AppointmentPaymentStatus.AwaitingBankTransferReceipt)]
    [InlineData("PaymentGateway", AppointmentPaymentStatus.AwaitingGatewayPayment)]
    public async Task MethodSelectionPersistsTheAppointmentOwnerAmountAndUnpaidStatus(string method, AppointmentPaymentStatus status)
    {
        using var f = new PaymentFixture();
        await f.Select(method); f.Db.ChangeTracker.Clear();
        var saved = await f.Db.AppointmentPayments.SingleAsync();
        Assert.Equal(1, saved.AppointmentId); Assert.Equal(PaymentFixture.Patient, saved.PatientId);
        Assert.Equal(2700m, saved.Amount); Assert.Equal(method, saved.Method.ToString()); Assert.Equal(status, saved.Status);
    }

    [Fact]
    public async Task AnotherPatientCannotReadChangeOrUploadToThePayment()
    {
        using var f = new PaymentFixture(); await f.Select("BankTransfer"); var stranger = Guid.NewGuid();
        Assert.Null(await f.Payments.GetPaymentAsync(stranger, 1));
        await Assert.ThrowsAsync<KeyNotFoundException>(() => f.Payments.SelectPaymentMethodAsync(stranger, 1, new() { Method = "Cash" }));
        await Assert.ThrowsAsync<KeyNotFoundException>(() => f.Payments.UploadReceiptAsync(stranger, 1, PaymentFixture.Receipt()));
        Assert.Empty(f.Storage.Files); Assert.Empty(f.Db.AppointmentReceipts);
    }

    [Theory]
    [InlineData(true, AppointmentPaymentStatus.Successful, AppointmentReceiptStatus.Verified)]
    [InlineData(false, AppointmentPaymentStatus.AwaitingBankTransferReceipt, AppointmentReceiptStatus.Rejected)]
    public async Task StaffDecisionPersistsReceiptAuditAndPaymentStatus(bool approve, AppointmentPaymentStatus status, AppointmentReceiptStatus receiptStatus)
    {
        using var f = new PaymentFixture(); await f.Select("BankTransfer");
        await f.Payments.UploadReceiptAsync(PaymentFixture.Patient, 1, PaymentFixture.Receipt());
        Assert.Equal(AppointmentPaymentStatus.ReceiptUnderVerification, (await f.Db.AppointmentPayments.SingleAsync()).Status);
        await f.Payments.VerifyReceiptAsync(PaymentFixture.Staff, 1, new() { Approved = approve, RejectionReason = approve ? null : "Amount does not match" });
        f.Db.ChangeTracker.Clear(); var payment = await f.Db.AppointmentPayments.SingleAsync(); var receipt = await f.Db.AppointmentReceipts.SingleAsync();
        Assert.Equal(status, payment.Status); Assert.Equal(receiptStatus, receipt.Status);
        Assert.Equal(payment.Id, receipt.AppointmentPaymentId); Assert.Equal(1, receipt.AppointmentId);
        Assert.Equal(PaymentFixture.Patient, receipt.PatientId); Assert.Equal(PaymentFixture.Staff, receipt.ReviewedBy);
        Assert.NotNull(receipt.ReviewedAtUtc); Assert.True(f.Storage.Files.ContainsKey(receipt.BlobName));
        if (!approve) Assert.Equal("Amount does not match", receipt.RejectionReason);
    }

    [Fact]
    public async Task RejectedReceiptCanBeReplacedButCannotBeApprovedWithoutNewUpload()
    {
        using var f = new PaymentFixture(); await f.Select("BankTransfer");
        await f.Payments.UploadReceiptAsync(PaymentFixture.Patient, 1, PaymentFixture.Receipt());
        await f.Payments.VerifyReceiptAsync(PaymentFixture.Staff, 1, new() { Approved = false, RejectionReason = "Wrong amount" });
        await Assert.ThrowsAsync<InvalidOperationException>(() => f.Payments.VerifyReceiptAsync(PaymentFixture.Staff, 1, new() { Approved = true }));
        await f.Payments.UploadReceiptAsync(PaymentFixture.Patient, 1, PaymentFixture.Receipt());
        Assert.Equal(2, await f.Db.AppointmentReceipts.CountAsync());
        Assert.Equal(AppointmentPaymentStatus.ReceiptUnderVerification, (await f.Db.AppointmentPayments.SingleAsync()).Status);
    }

    [Theory]
    [InlineData("text/plain", "receipt.txt")]
    [InlineData("application/pdf", "receipt.pdf")]
    [InlineData("image/png", "receipt.png")]
    public async Task InvalidReceiptContentCannotEnterVerification(string type, string name)
    {
        using var f = new PaymentFixture(); await f.Select("BankTransfer");
        await Assert.ThrowsAsync<ArgumentException>(() => f.Payments.UploadReceiptAsync(PaymentFixture.Patient, 1, PaymentFixture.Receipt([1, 2, 3], type, name)));
        Assert.Empty(f.Db.AppointmentReceipts); Assert.Empty(f.Storage.Files);
        Assert.Equal(AppointmentPaymentStatus.AwaitingBankTransferReceipt, (await f.Db.AppointmentPayments.SingleAsync()).Status);
    }

    [Fact]
    public async Task RecognizedImageContentIsStoredUnmodifiedForStaffReview()
    {
        using var f = new PaymentFixture(); await f.Select("BankTransfer");
        var bytes = Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK1sAAAAASUVORK5CYII=");
        await f.Payments.UploadReceiptAsync(PaymentFixture.Patient, 1, PaymentFixture.Receipt(bytes, "image/png", "receipt.png"));
        var receipt = await f.Db.AppointmentReceipts.SingleAsync();
        Assert.Equal(bytes, f.Storage.Files[receipt.BlobName]);
        Assert.Equal(AppointmentReceiptStatus.PendingVerification, receipt.Status);
        Assert.Equal(AppointmentPaymentStatus.ReceiptUnderVerification, (await f.Db.AppointmentPayments.SingleAsync()).Status);
    }

    [Fact]
    public async Task OversizedReceiptIsRejectedBeforeStorage()
    {
        using var f = new PaymentFixture(); await f.Select("BankTransfer");
        await Assert.ThrowsAsync<ArgumentException>(() => f.Payments.UploadReceiptAsync(PaymentFixture.Patient, 1, PaymentFixture.Receipt(new byte[5 * 1024 * 1024 + 1])));
        Assert.Empty(f.Storage.Files); Assert.Empty(f.Db.AppointmentReceipts);
    }

    [Fact]
    public async Task StorageFailureLeavesThePaymentAwaitingReceiptAndAllowsRetry()
    {
        using var f = new PaymentFixture(); await f.Select("BankTransfer"); f.Storage.FailUploads = true;
        await Assert.ThrowsAsync<IOException>(() => f.Payments.UploadReceiptAsync(PaymentFixture.Patient, 1, PaymentFixture.Receipt()));
        Assert.Empty(f.Db.AppointmentReceipts);
        Assert.Equal(AppointmentPaymentStatus.AwaitingBankTransferReceipt, (await f.Db.AppointmentPayments.SingleAsync()).Status);
        f.Storage.FailUploads = false;
        var saved = await f.Payments.UploadReceiptAsync(PaymentFixture.Patient, 1, PaymentFixture.Receipt());
        Assert.Equal("ReceiptUnderVerification", saved.Status);
    }

    [Theory]
    [InlineData(AppointmentPaymentStatus.Successful)]
    [InlineData(AppointmentPaymentStatus.ReceiptUnderVerification)]
    public async Task PaidOrUnderReviewPaymentCannotChangeMethod(AppointmentPaymentStatus status)
    {
        using var f = new PaymentFixture(); await f.Select("BankTransfer");
        (await f.Db.AppointmentPayments.SingleAsync()).Status = status; await f.Db.SaveChangesAsync();
        await Assert.ThrowsAsync<InvalidOperationException>(() => f.Select("Cash"));
        Assert.Equal(AppointmentPaymentMethod.BankTransfer, (await f.Db.AppointmentPayments.SingleAsync()).Method);
    }
}
