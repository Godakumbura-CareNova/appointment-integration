using System.Net.Http.Json;
using System.Text.Json;
using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Models;
using Microsoft.Extensions.DependencyInjection;

namespace AppointmentIntegration.Api.Tests.Integration;

public class AdminAppointmentListTests
{
    [Theory]
    [InlineData(null, 401)] [InlineData("Patient", 403)] [InlineData("Doctor", 403)]
    [InlineData("PharmacyStaff", 403)] [InlineData("Admin", 200)]
    public async Task OnlyAdminCanList(string? role, int expected)
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(); using var client = factory.Client(role);
        Assert.Equal(expected, (int)(await client.GetAsync("/api/admin/appointments")).StatusCode);
    }

    [Fact]
    public async Task ListsAcrossDoctorsWithPagingAndOwnershipMatchedPayment()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true);
        var patient = Guid.NewGuid();
        using (var scope = factory.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
            await db.Database.EnsureCreatedAsync();
            for (var i = 1; i <= 3; i++) db.Appointments.Add(new() { Id = i, AppointmentReference = "APT-" + i,
                DoctorName = "Dr Test", DoctorId = Guid.NewGuid(), PatientId = patient, AppointmentStartUtc = DateTime.UtcNow.AddDays(i),
                AppointmentEndUtc = DateTime.UtcNow.AddDays(i).AddMinutes(30), CreatedAtUtc = DateTime.UtcNow.Date, DoctorAvailabilitySlotId = i });
            db.AppointmentPayments.Add(new() { AppointmentId = 3, PatientId = Guid.NewGuid(), Status = AppointmentPaymentStatus.Successful });
            await db.SaveChangesAsync();
        }
        using var client = factory.Client("Admin");
        var response = await client.GetAsync("/api/admin/appointments?search=APT-&page=1&pageSize=2");
        Assert.Equal(200, (int)response.StatusCode);
        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(3, json.GetProperty("totalCount").GetInt32());
        var rows = json.GetProperty("items").EnumerateArray().ToArray();
        Assert.Equal(new[] { 3, 2 }, rows.Select(x => x.GetProperty("id").GetInt32()));
        Assert.Equal(patient, rows[0].GetProperty("patientId").GetGuid());
        Assert.Equal(JsonValueKind.Null, rows[0].GetProperty("paymentStatus").ValueKind);
        Assert.Equal(400, (int)(await client.GetAsync("/api/admin/appointments?page=0")).StatusCode);
    }
}
