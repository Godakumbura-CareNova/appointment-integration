using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Models;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace AppointmentIntegration.Api.Tests.Integration;

public class StaffAppointmentTransactionsTests
{
    private const string Path = "/api/staff/appointment-payments/transactions";

    [Fact]
    public async Task RelationalHistoryIncludesAllMethodsWithCorrectCountsFilteringAndStablePaging()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true);
        await Seed(factory);
        using var staff = factory.Client("PharmacyStaff");
        var all = await staff.GetFromJsonAsync<JsonElement>(Path + "?pageSize=2");
        Assert.Equal(7, all.GetProperty("totalCount").GetInt32());
        Assert.Equal(4, all.GetProperty("totalPages").GetInt32());
        var counts = all.GetProperty("counts");
        Assert.Equal(7, counts.GetProperty("all").GetInt32());
        Assert.Equal(4, counts.GetProperty("pending").GetInt32());
        Assert.Equal(1, counts.GetProperty("successful").GetInt32());
        Assert.Equal(1, counts.GetProperty("failed").GetInt32());
        Assert.Equal(1, counts.GetProperty("rejected").GetInt32());
        Assert.Equal(new[] {7, 6}, all.GetProperty("transactions").EnumerateArray().Select(x => x.GetProperty("id").GetInt32()));
        var second = await staff.GetFromJsonAsync<JsonElement>(Path + "?page=2&pageSize=2");
        Assert.Equal(new[] {5, 4}, second.GetProperty("transactions").EnumerateArray().Select(x => x.GetProperty("id").GetInt32()));
        var filtered = await staff.GetFromJsonAsync<JsonElement>(Path + "?method=BankTransfer&status=Rejected&search=Dr%20Test");
        Assert.Equal(1, filtered.GetProperty("totalCount").GetInt32());
        Assert.Equal(3, filtered.GetProperty("transactions")[0].GetProperty("id").GetInt32());
        Assert.Equal(3, filtered.GetProperty("counts").GetProperty("all").GetInt32());
        var empty = await staff.GetFromJsonAsync<JsonElement>(Path + "?search=does-not-exist&page=50");
        Assert.Equal(0, empty.GetProperty("totalCount").GetInt32());
        Assert.Equal(1, empty.GetProperty("page").GetInt32());
        var clamped = await staff.GetFromJsonAsync<JsonElement>(Path + "?page=50&pageSize=2");
        Assert.Equal(4, clamped.GetProperty("page").GetInt32());
    }

    [Fact]
    public async Task DetailsExposeSafeHistoryAndReuploadedReceiptNoLongerCountsAsRejected()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true);
        await Seed(factory);
        using var staff = factory.Client("PharmacyStaff");
        var response = await staff.GetAsync(Path + "/3");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await response.Content.ReadAsStringAsync();
        var details = JsonSerializer.Deserialize<JsonElement>(body);
        Assert.Equal("Rejected", details.GetProperty("transaction").GetProperty("category").GetString());
        Assert.Equal("Rejected", details.GetProperty("receipts")[0].GetProperty("status").GetString());
        Assert.DoesNotContain("private-blob", body);
        Assert.DoesNotContain("containerName", body);
        Assert.Equal(HttpStatusCode.NotFound, (await staff.GetAsync(Path + "/999")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await staff.GetAsync(Path + "/8")).StatusCode); // owner mismatch
        using (var scope = factory.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
            var p = await db.AppointmentPayments.FindAsync(3);
            p!.Status = AppointmentPaymentStatus.ReceiptUnderVerification;
            db.AppointmentReceipts.Add(new() { AppointmentPaymentId=3, AppointmentId=3, PatientId=p.PatientId,
                Status=AppointmentReceiptStatus.PendingVerification, UploadedAtUtc=DateTime.UtcNow.AddDays(1), OriginalFileName="new.pdf" });
            await db.SaveChangesAsync();
        }
        var rejected = await staff.GetFromJsonAsync<JsonElement>(Path + "?status=Rejected");
        Assert.Equal(0, rejected.GetProperty("totalCount").GetInt32());
        var pending = await staff.GetFromJsonAsync<JsonElement>(Path + "?status=Pending");
        Assert.Equal(5, pending.GetProperty("totalCount").GetInt32());
        var online = await staff.GetFromJsonAsync<JsonElement>(Path + "/2");
        Assert.Equal("Failed", online.GetProperty("onlineAttempts")[0].GetProperty("status").GetString());
    }

    [Theory]
    [InlineData(null, 401)] [InlineData("Patient", 403)] [InlineData("Doctor", 403)] [InlineData("Admin", 403)]
    public async Task HistoryAndDetailsAreStaffOnly(string? role, int expected)
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory();
        await Seed(factory);
        using var client = factory.Client(role);
        Assert.Equal(expected, (int)(await client.GetAsync(Path)).StatusCode);
        Assert.Equal(expected, (int)(await client.GetAsync(Path + "/1")).StatusCode);
    }

    [Theory]
    [InlineData("status=Unknown")] [InlineData("method=1")] [InlineData("method=Online")] [InlineData("page=0")] [InlineData("pageSize=101")]
    public async Task InvalidFiltersAreRejected(string query)
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory();
        await Seed(factory);
        using var staff = factory.Client("PharmacyStaff");
        Assert.Equal(HttpStatusCode.BadRequest, (await staff.GetAsync(Path + "?" + query)).StatusCode);
    }

    private static async Task Seed(AppointmentPaymentsIntegrationTests.PaymentApiFactory factory)
    {
        await factory.Seed();
        using var scope = factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        var owner = (await db.Appointments.SingleAsync()).PatientId;
        var now = DateTime.UtcNow;
        var statuses = new[] { AppointmentPaymentStatus.Successful, AppointmentPaymentStatus.Failed,
            AppointmentPaymentStatus.AwaitingBankTransferReceipt, AppointmentPaymentStatus.AwaitingBankTransferReceipt,
            AppointmentPaymentStatus.ReceiptUnderVerification, AppointmentPaymentStatus.AwaitingGatewayPayment,
            AppointmentPaymentStatus.Pending, AppointmentPaymentStatus.Successful };
        for (var id = 1; id <= 8; id++)
        {
            if (id > 1) db.Appointments.Add(new() { Id=id, AppointmentReference=$"APT-{id}", PatientId=owner, DoctorId=Guid.NewGuid(),
                DoctorName="Dr Test", DoctorAvailabilitySlotId=100+id, AppointmentStartUtc=now, AppointmentEndUtc=now.AddMinutes(30), CreatedAtUtc=now });
            db.AppointmentPayments.Add(new() { Id=id, AppointmentId=id, PatientId=id==8?Guid.NewGuid():owner, Amount=2700,
                Status=statuses[id-1], Method=id is 3 or 4 or 5 ? AppointmentPaymentMethod.BankTransfer : id==7 ? AppointmentPaymentMethod.Cash : AppointmentPaymentMethod.PaymentGateway,
                CreatedAtUtc=now, UpdatedAtUtc=now, ConfirmedAtUtc=id==1?now:null });
        }
        await db.SaveChangesAsync();
        db.AppointmentReceipts.Add(new() { AppointmentPaymentId=3, AppointmentId=3, PatientId=owner, Status=AppointmentReceiptStatus.Rejected,
            OriginalFileName="receipt.pdf", BlobName="private-blob", ContainerName="private-container", UploadedAtUtc=now, RejectionReason="Amount mismatch" });
        db.AppointmentOnlinePaymentAttempts.Add(new() { AppointmentPaymentId=2, AppointmentId=2, PatientId=owner,
            AttemptNumber=1, GatewayReference="private-gateway", Status=AppointmentOnlinePaymentAttemptStatus.Failed, CreatedAtUtc=now, Amount=2700 });
        await db.SaveChangesAsync();
    }
}
