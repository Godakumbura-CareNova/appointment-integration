using AppointmentIntegration.Api.Exceptions;
using AppointmentIntegration.Api.Models;
using AppointmentIntegration.Api.Tests.Support;
using Microsoft.EntityFrameworkCore;

namespace AppointmentIntegration.Api.Tests.Unit;

public class AppointmentOnlinePaymentServiceTests
{
    [Fact]
    public async Task SignedSuccessPersistsAgainstTheCorrectAppointmentAndDuplicateCallbackIsHarmless()
    {
        using var f = new PaymentFixture(); await f.Select("PaymentGateway"); var session = await f.Start();
        Assert.Equal("2700.00", session.Amount); Assert.True(session.Sandbox);
        Assert.Equal("AwaitingGatewayPayment", (await f.Payments.GetPaymentAsync(PaymentFixture.Patient, 1))!.Status);
        var callback = f.Notification(session.GatewayOrderId);
        await f.Online.HandleNotificationAsync(callback);
        var confirmedAt = (await f.Db.AppointmentPayments.AsNoTracking().SingleAsync()).ConfirmedAtUtc;
        await f.Online.HandleNotificationAsync(callback);
        f.Db.ChangeTracker.Clear(); var payment = await f.Db.AppointmentPayments.SingleAsync(); var attempt = await f.Db.AppointmentOnlinePaymentAttempts.SingleAsync();
        Assert.Equal(AppointmentPaymentStatus.Successful, payment.Status); Assert.Equal(AppointmentOnlinePaymentAttemptStatus.Succeeded, attempt.Status);
        Assert.NotNull(payment.ConfirmedAtUtc);
        Assert.Equal(confirmedAt, payment.ConfirmedAtUtc);
        Assert.Equal(payment.Id, attempt.AppointmentPaymentId); Assert.Equal(payment.AppointmentId, attempt.AppointmentId);
        Assert.Equal(PaymentFixture.Patient, attempt.PatientId); Assert.Equal("TEST-TRANSACTION", attempt.GatewayPaymentId);
        Assert.False((await f.Online.GetResultAsync(PaymentFixture.Patient, 1, attempt.Id)).CanRetry);
    }

    [Fact]
    public async Task ForgedSignatureNeverConfirmsPayment()
    {
        using var f = new PaymentFixture(); await f.Select("PaymentGateway"); var session = await f.Start();
        var callback = f.Notification(session.GatewayOrderId); callback["md5sig"] = new string('0', 32);
        await Assert.ThrowsAsync<InvalidWebhookSignatureException>(() => f.Online.HandleNotificationAsync(callback));
        Assert.Equal(AppointmentPaymentStatus.AwaitingGatewayPayment, (await f.Db.AppointmentPayments.SingleAsync()).Status);
        Assert.Equal(AppointmentOnlinePaymentAttemptStatus.Pending, (await f.Db.AppointmentOnlinePaymentAttempts.SingleAsync()).Status);
    }

    [Theory]
    [InlineData("1.00", "LKR")]
    [InlineData("2700.00", "USD")]
    public async Task SignedButMismatchedPaymentIsNotSuccessful(string amount, string currency)
    {
        using var f = new PaymentFixture(); await f.Select("PaymentGateway"); var session = await f.Start();
        await f.Online.HandleNotificationAsync(f.Notification(session.GatewayOrderId, amount, currency));
        f.Db.ChangeTracker.Clear();
        Assert.Equal(AppointmentPaymentStatus.Failed, (await f.Db.AppointmentPayments.SingleAsync()).Status);
        Assert.Equal("verification_failed", (await f.Db.AppointmentOnlinePaymentAttempts.SingleAsync()).FailureCode);
    }

    [Theory]
    [InlineData("-1")]
    [InlineData("-2")]
    public async Task FailedOrCancelledTransactionCanBeRetriedWithANewReference(string code)
    {
        using var f = new PaymentFixture(); await f.Select("PaymentGateway"); var first = await f.Start();
        await f.Online.HandleNotificationAsync(f.Notification(first.GatewayOrderId, status: code));
        var result = await f.Online.GetResultAsync(PaymentFixture.Patient, 1, first.AttemptId);
        Assert.True(result.CanRetry); Assert.NotEqual("Succeeded", result.Outcome);
        var second = await f.Start(); Assert.Equal(2, second.AttemptNumber); Assert.NotEqual(first.GatewayOrderId, second.GatewayOrderId);
        Assert.Equal(2, await f.Db.AppointmentOnlinePaymentAttempts.CountAsync());
    }

    [Fact]
    public async Task RetryLimitPreventsCreatingAdditionalTransactions()
    {
        using var f = new PaymentFixture(); await f.Select("PaymentGateway");
        for (var i = 0; i < 3; i++) { var session = await f.Start(); await f.Online.HandleNotificationAsync(f.Notification(session.GatewayOrderId, status: "-2")); }
        await Assert.ThrowsAsync<InvalidOperationException>(() => f.Start());
        Assert.Equal(3, await f.Db.AppointmentOnlinePaymentAttempts.CountAsync());
    }

    [Fact]
    public async Task AnotherPatientCannotStartReadOrCancelAnAttempt()
    {
        using var f = new PaymentFixture(); await f.Select("PaymentGateway"); var session = await f.Start(); var stranger = Guid.NewGuid();
        await Assert.ThrowsAsync<KeyNotFoundException>(() => f.Online.StartAsync(stranger, 1, PaymentFixture.Billing(), null));
        await Assert.ThrowsAsync<KeyNotFoundException>(() => f.Online.GetResultAsync(stranger, 1, session.AttemptId));
        await Assert.ThrowsAsync<KeyNotFoundException>(() => f.Online.CancelAsync(stranger, 1, session.AttemptId));
        Assert.Equal(AppointmentOnlinePaymentAttemptStatus.Pending, (await f.Db.AppointmentOnlinePaymentAttempts.SingleAsync()).Status);
    }

    [Fact]
    public async Task LateFailureFromReplacedAttemptCannotUndoSuccessfulPayment()
    {
        using var f = new PaymentFixture(); await f.Select("PaymentGateway"); var old = await f.Start(); var current = await f.Start();
        await f.Online.HandleNotificationAsync(f.Notification(current.GatewayOrderId));
        await f.Online.HandleNotificationAsync(f.Notification(old.GatewayOrderId, status: "-2"));
        f.Db.ChangeTracker.Clear(); Assert.Equal(AppointmentPaymentStatus.Successful, (await f.Db.AppointmentPayments.SingleAsync()).Status);
    }

    [Fact]
    public async Task CallbackAfterSwitchingToCashCannotConfirmOrFailTheCashPayment()
    {
        using var f = new PaymentFixture(); await f.Select("PaymentGateway"); var session = await f.Start();
        await f.Select("Cash");
        Assert.False(await f.Online.HandleNotificationAsync(f.Notification(session.GatewayOrderId)));
        f.Db.ChangeTracker.Clear(); var saved = await f.Db.AppointmentPayments.SingleAsync();
        Assert.Equal(AppointmentPaymentMethod.Cash, saved.Method);
        Assert.Equal(AppointmentPaymentStatus.Pending, saved.Status);
    }

    [Fact]
    public async Task CallbackForAnOutdatedAmountCannotConfirmCurrentPayment()
    {
        using var f = new PaymentFixture(); await f.Select("PaymentGateway"); var session = await f.Start();
        (await f.Db.AppointmentPayments.SingleAsync()).Amount = 3000m; await f.Db.SaveChangesAsync();
        await f.Online.HandleNotificationAsync(f.Notification(session.GatewayOrderId));
        f.Db.ChangeTracker.Clear(); Assert.NotEqual(AppointmentPaymentStatus.Successful, (await f.Db.AppointmentPayments.SingleAsync()).Status);
    }
}
