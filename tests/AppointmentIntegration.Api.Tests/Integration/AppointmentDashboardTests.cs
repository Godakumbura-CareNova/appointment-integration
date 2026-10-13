using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Models;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace AppointmentIntegration.Api.Tests.Integration;

public class AppointmentDashboardTests
{
    [Fact]
    public async Task PatientUpcoming_IsOwnedActiveAndFuture_WithCompleteCountAndFiveRows()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true);
        await factory.Seed();
        using (var scope = factory.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
            var original = await db.Appointments.SingleAsync();
            for (var i = 2; i <= 11; i++) db.Appointments.Add(new()
            {
                Id = i, PatientId = i == 11 ? Guid.NewGuid() : original.PatientId, DoctorId = original.DoctorId,
                DoctorName = "Dr Test", AppointmentReference = $"APT-{i}", DoctorAvailabilitySlotId = i + 50,
                AppointmentStartUtc = DateTime.UtcNow.AddDays(i == 10 ? -1 : i), AppointmentEndUtc = DateTime.UtcNow.AddDays(i).AddHours(1),
                Status = i == 9 ? AppointmentStatus.Cancelled : i == 8 ? AppointmentStatus.Completed : AppointmentStatus.Confirmed
            });
            await db.SaveChangesAsync();
        }
        using var patient = factory.Client("Patient");
        var response = await patient.GetAsync("/api/patient/dashboard/appointments");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(6, json.GetProperty("upcomingCount").GetInt32());
        Assert.Equal(new[] { 2, 3, 4, 5, 6 }, json.GetProperty("appointments").EnumerateArray().Select(x => x.GetProperty("id").GetInt32()));
        using var other = factory.Client("Patient", Guid.NewGuid());
        var empty = await other.GetFromJsonAsync<JsonElement>("/api/patient/dashboard/appointments");
        Assert.Equal(0, empty.GetProperty("upcomingCount").GetInt32());
    }

    [Theory]
    [InlineData(null, "/api/patient/dashboard/appointments", HttpStatusCode.Unauthorized)]
    [InlineData("Doctor", "/api/patient/dashboard/appointments", HttpStatusCode.Forbidden)]
    [InlineData("Patient", "/api/staff/dashboard/appointment-payments", HttpStatusCode.Forbidden)]
    [InlineData("Admin", "/api/staff/dashboard/appointment-payments", HttpStatusCode.Forbidden)]
    public async Task Dashboard_EnforcesRoles(string? role, string route, HttpStatusCode expected)
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory();
        using var client = factory.Client(role);
        Assert.Equal(expected, (await client.GetAsync(route)).StatusCode);
    }
}
