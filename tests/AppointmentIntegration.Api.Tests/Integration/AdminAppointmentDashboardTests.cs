using System.Net.Http.Json;
using System.Text.Json;
using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Models;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Time.Testing;
using AppointmentIntegration.Api.Services;

namespace AppointmentIntegration.Api.Tests.Integration;

public class AdminAppointmentDashboardTests
{
    [Fact]
    public async Task TodayUsesSriLankaDateAndUpcomingExcludesTerminalStatuses()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true);
        using var scope = factory.Services.CreateScope(); var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        await db.Database.EnsureCreatedAsync();
        var now = new DateTime(2026, 11, 1, 1, 0, 0, DateTimeKind.Utc);
        var starts = new[] { new DateTime(2026, 10, 31, 18, 29, 59, DateTimeKind.Utc), new DateTime(2026, 10, 31, 18, 30, 0, DateTimeKind.Utc),
            new DateTime(2026, 11, 1, 18, 29, 59, DateTimeKind.Utc), new DateTime(2026, 11, 1, 18, 30, 0, DateTimeKind.Utc), now.AddDays(2), now.AddDays(2), now.AddDays(2) };
        for (var i = 0; i < starts.Length; i++) db.Appointments.Add(new() { Id = i + 1, AppointmentReference = $"APT-{i}", DoctorAvailabilitySlotId = i + 1,
            PatientId = Guid.NewGuid(), DoctorId = Guid.NewGuid(), CreatedAtUtc = now, AppointmentStartUtc = starts[i], AppointmentEndUtc = starts[i].AddMinutes(30),
            Status = i == 4 ? AppointmentStatus.Cancelled : i == 5 ? AppointmentStatus.Completed : i == 6 ? AppointmentStatus.NoShow : AppointmentStatus.Booked });
        await db.SaveChangesAsync();
        var result = await new AppointmentDashboardService(db, new FakeTimeProvider(new DateTimeOffset(now))).GetAdminAppointmentsAsync(default);
        Assert.Equal(7, result.TotalAppointments); Assert.Equal(2, result.TodayCount); Assert.Equal(2, result.UpcomingCount);
        Assert.Equal(new[] { 7, 6, 5, 4, 3 }, result.RecentAppointments.Select(a => a.Id));
    }

    [Theory]
    [InlineData(null, 401)] [InlineData("Patient", 403)] [InlineData("User", 403)] [InlineData("Doctor", 403)]
    [InlineData("PharmacyStaff", 403)] [InlineData("Pharmacy Staff", 403)] [InlineData("Admin", 200)]
    public async Task BothEndpointsAreAdminOnlyAndEmpty(string? role, int status)
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory();
        using (var scope = factory.Services.CreateScope()) await scope.ServiceProvider.GetRequiredService<AppDbContext>().Database.EnsureCreatedAsync();
        using var client = factory.Client(role);
        foreach (var endpoint in new[] { "appointments", "appointment-payments" })
        {
            var response = await client.GetAsync($"/api/admin/dashboard/{endpoint}");
            Assert.True(status == (int)response.StatusCode, $"{endpoint}: expected {status}, got {(int)response.StatusCode}");
            if (status == 200)
            {
                var json = await response.Content.ReadFromJsonAsync<JsonElement>();
                Assert.Equal(0, json.GetProperty(endpoint == "appointments" ? "totalAppointments" : "totalPayments").GetInt32());
            }
        }
    }

    [Fact]
    public async Task AppointmentSummaryCountsAcrossDoctorsWithBoundedRowsAndMatchingPayments()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true);
        await factory.Seed();
        using (var scope = factory.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
            for (var i = 2; i <= 7; i++) db.Appointments.Add(new() { Id = i, AppointmentReference = $"APT-{i}", PatientId = Guid.NewGuid(), DoctorId = Guid.NewGuid(),
                DoctorName = $"Doctor {i}", DoctorAvailabilitySlotId = 20 + i, CreatedAtUtc = DateTime.UtcNow,
                AppointmentStartUtc = DateTime.UtcNow.AddDays(2), AppointmentEndUtc = DateTime.UtcNow.AddDays(2).AddHours(1),
                Status = i == 6 ? AppointmentStatus.Completed : AppointmentStatus.Confirmed });
            await db.SaveChangesAsync();
            var a = await db.Appointments.SingleAsync(a => a.Id == 7);
            db.AppointmentPayments.Add(new() { AppointmentId = 7, PatientId = Guid.NewGuid(), Status = AppointmentPaymentStatus.Successful }); // mismatched owner must not enrich
            await db.SaveChangesAsync();
            await db.Database.ExecuteSqlRawAsync("UPDATE Appointments SET Status='HistoricalStatus' WHERE Id=7");
        }
        using var client = factory.Client("Admin");
        var response = await client.GetAsync("/api/admin/dashboard/appointments");
        Assert.Equal(200, (int)response.StatusCode);
        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(7, json.GetProperty("totalAppointments").GetInt32());
        Assert.Equal(1, json.GetProperty("statusCounts").GetProperty("Unavailable").GetInt32());
        var rows = json.GetProperty("recentAppointments").EnumerateArray().ToArray();
        Assert.Equal(5, rows.Length); Assert.Equal(7, rows[0].GetProperty("id").GetInt32());
        Assert.Equal(JsonValueKind.Null, rows[0].GetProperty("paymentStatus").ValueKind);
        Assert.DoesNotContain("patientId", await response.Content.ReadAsStringAsync());
    }
}
