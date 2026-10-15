using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using AppointmentIntegration.Api.Data;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace AppointmentIntegration.Api.Tests.Integration;

public class PatientReceiptRejectionFeedbackTests
{
    private const string Notifications = "/api/patient/appointment-notifications";
    private const string Payment = "/api/appointments/1/payment";

    [Fact]
    public async Task RejectionReasonIsOwnedPersistentAndReplacedByNewUploadWithoutDuplicateNotifications()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true);
        await factory.Seed();
        using (var scope = factory.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
            var appointment = await db.Appointments.SingleAsync();
            appointment.AppointmentStartUtc = DateTime.UtcNow.AddDays(10);
            appointment.AppointmentEndUtc = appointment.AppointmentStartUtc.AddMinutes(30);
            await db.SaveChangesAsync();
        }
        using var patient = factory.Client("Patient");
        using var staff = factory.Client("PharmacyStaff");
        using var stranger = factory.Client("Patient", Guid.NewGuid());
        Assert.Equal(HttpStatusCode.OK, (await patient.PostAsJsonAsync(Payment + "/method", new { method = "BankTransfer" })).StatusCode);
        using (var form = Receipt()) Assert.Equal(HttpStatusCode.OK, (await patient.PostAsync(Payment + "/receipt", form)).StatusCode);
        const string review = "/api/staff/appointment-payments/appointments/1/receipt/verify";
        Assert.Equal(HttpStatusCode.OK, (await staff.PostAsJsonAsync(review, new { approved = false, rejectionReason = "Amount does not match" })).StatusCode);

        var payment = await patient.GetFromJsonAsync<JsonElement>(Payment);
        Assert.Equal("AwaitingBankTransferReceipt", payment.GetProperty("status").GetString());
        Assert.Equal("Rejected", payment.GetProperty("latestReceipt").GetProperty("status").GetString());
        Assert.Equal("Amount does not match", payment.GetProperty("latestReceipt").GetProperty("rejectionReason").GetString());
        Assert.EndsWith("Z", payment.GetProperty("latestReceipt").GetProperty("reviewedAtUtc").GetString());
        foreach (var endpoint in new[] { "/api/appointments", "/api/appointments/1" })
        {
            var data = await patient.GetFromJsonAsync<JsonElement>(endpoint);
            var item = endpoint.EndsWith("/1") ? data : data[0];
            Assert.Equal("Amount does not match", item.GetProperty("latestReceipt").GetProperty("rejectionReason").GetString());
            Assert.True(item.GetProperty("canPay").GetBoolean());
        }
        Assert.Equal(HttpStatusCode.NotFound, (await stranger.GetAsync(Payment)).StatusCode);
        Assert.Empty((await stranger.GetFromJsonAsync<JsonElement>(Notifications)).EnumerateArray());
        var notifications = await patient.GetFromJsonAsync<JsonElement>(Notifications);
        var notification = Assert.Single(notifications.EnumerateArray());
        var id = notification.GetProperty("id").GetInt32();
        Assert.Contains("Amount does not match", notification.GetProperty("message").GetString());
        Assert.False(notification.GetProperty("isRead").GetBoolean());
        Assert.Equal(HttpStatusCode.NotFound, (await stranger.PostAsync($"{Notifications}/{id}/read", null)).StatusCode);
        Assert.Equal(HttpStatusCode.NoContent, (await patient.PostAsync($"{Notifications}/{id}/read", null)).StatusCode);
        Assert.Equal(HttpStatusCode.NoContent, (await patient.PostAsync($"{Notifications}/{id}/read", null)).StatusCode);
        using var freshClient = factory.Client("Patient");
        Assert.True((await freshClient.GetFromJsonAsync<JsonElement>(Notifications))[0].GetProperty("isRead").GetBoolean());
        // Repeating a completed staff review must not create another notification.
        Assert.Equal(HttpStatusCode.Conflict, (await staff.PostAsJsonAsync(review, new { approved = false, rejectionReason = "Duplicate" })).StatusCode);
        Assert.Single((await patient.GetFromJsonAsync<JsonElement>(Notifications)).EnumerateArray());

        using (var form = Receipt()) Assert.Equal(HttpStatusCode.OK, (await patient.PostAsync(Payment + "/receipt", form)).StatusCode);
        var reuploaded = await patient.GetFromJsonAsync<JsonElement>(Payment);
        Assert.Equal("ReceiptUnderVerification", reuploaded.GetProperty("status").GetString());
        Assert.Equal("PendingVerification", reuploaded.GetProperty("latestReceipt").GetProperty("status").GetString());
        Assert.Equal(JsonValueKind.Null, reuploaded.GetProperty("latestReceipt").GetProperty("rejectionReason").ValueKind);
        var detail = await patient.GetFromJsonAsync<JsonElement>("/api/appointments/1");
        Assert.Equal("PendingVerification", detail.GetProperty("latestReceipt").GetProperty("status").GetString());
        Assert.DoesNotContain("Please upload", (await patient.GetFromJsonAsync<JsonElement>(Notifications))[0].GetProperty("message").GetString());
        Assert.Equal(HttpStatusCode.OK, (await staff.PostAsJsonAsync(review, new { approved = false, rejectionReason = "Receipt unreadable" })).StatusCode);
        Assert.Equal(HttpStatusCode.NoContent, (await stranger.PostAsync(Notifications + "/read-all", null)).StatusCode);
        Assert.Contains((await patient.GetFromJsonAsync<JsonElement>(Notifications)).EnumerateArray(), n => !n.GetProperty("isRead").GetBoolean());
        Assert.Equal(HttpStatusCode.NoContent, (await patient.PostAsync(Notifications + "/read-all", null)).StatusCode);
        Assert.All((await patient.GetFromJsonAsync<JsonElement>(Notifications)).EnumerateArray(), n => Assert.True(n.GetProperty("isRead").GetBoolean()));
    }

    [Theory]
    [InlineData(null, 401)] [InlineData("PharmacyStaff", 403)] [InlineData("Doctor", 403)] [InlineData("Admin", 403)]
    public async Task NotificationEndpointsRejectNonPatients(string? role, int status)
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory();
        await factory.Seed();
        using var client = factory.Client(role);
        Assert.Equal(status, (int)(await client.GetAsync(Notifications)).StatusCode);
        Assert.Equal(status, (int)(await client.PostAsync(Notifications + "/1/read", null)).StatusCode);
        Assert.Equal(status, (int)(await client.PostAsync(Notifications + "/read-all", null)).StatusCode);
    }

    private static MultipartFormDataContent Receipt()
    {
        var form = new MultipartFormDataContent();
        var file = new ByteArrayContent(Encoding.ASCII.GetBytes("%PDF-1.4\nTest receipt\n%%EOF"));
        file.Headers.ContentType = new("application/pdf");
        form.Add(file, "receipt", "receipt.pdf"); return form;
    }
}
