using System.Net.Http.Json;
using System.Text.Json;
using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Models;
using Microsoft.Extensions.DependencyInjection;

namespace AppointmentIntegration.Api.Tests.Integration;
public class AdminAppointmentReportsTests
{
    private const string Path = "/api/admin/reports/appointment-income?from=2026-09-30T18:30:00Z&to=2026-10-01T18:30:00Z";
    [Theory]
    [InlineData(null, 401)] [InlineData("Patient", 403)] [InlineData("Doctor", 403)] [InlineData("PharmacyStaff", 403)] [InlineData("Admin", 200)]
    public async Task OnlyAdmin(string? role, int status)
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(); using var client = factory.Client(role);
        Assert.Equal(status, (int)(await client.GetAsync(Path)).StatusCode);
        if (role == "Admin") Assert.Equal(200, (int)(await client.GetAsync("/api/admin/reports/appointment-income?from=1999-12-26T18:30:00Z&to=2000-01-02T18:30:00Z")).StatusCode);
    }
    [Fact]
    public async Task GroupsBySriLankaDateExcludesReconciliationAndUndatedPayments()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory();
        using (var scope = factory.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
            for (var i = 1; i <= 5; i++) db.AppointmentPayments.Add(new() { Id = i, AppointmentId = i, PatientId = Guid.NewGuid(), Amount = 100,
                Status = i == 5 ? AppointmentPaymentStatus.Failed : AppointmentPaymentStatus.Successful,
                ConfirmedAtUtc = i == 3 ? null : i == 4 ? new DateTime(2026, 10, 1, 18, 30, 0, DateTimeKind.Utc) : new DateTime(2026, 9, 30, 18, 30, 0, DateTimeKind.Utc) });
            db.AppointmentPaymentReconciliations.Add(new() { PaymentId = 2, AppointmentId = 2 });
            await db.SaveChangesAsync();
        }
        using var client = factory.Client("Admin"); var response = await client.GetAsync(Path);
        Assert.Equal(200, (int)response.StatusCode);
        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(1, json.GetProperty("undatedSuccessfulCount").GetInt32());
        var day = Assert.Single(json.GetProperty("days").EnumerateArray());
        Assert.Equal("2026-10-01", day.GetProperty("date").GetString()); Assert.Equal(100, day.GetProperty("amount").GetDecimal());
        Assert.Equal(400, (int)(await client.GetAsync("/api/admin/reports/appointment-income?from=2026-10-01Z&to=2026-10-01Z")).StatusCode);
    }
}
