using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using AppointmentIntegration.Api.Data;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace AppointmentIntegration.Api.Tests.Integration;

public class DoctorAppointmentsIntegrationTests
{
    internal static readonly Guid Doctor = Guid.Parse("22222222-2222-2222-2222-222222222222");

    [Fact]
    public async Task ReadsAreOwnedAndPatientAccessDoesNotExposeUnassignedIds()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(true); await factory.Seed();
        using var doctor = factory.Client("Doctor", Doctor);
        using var other = factory.Client("Doctor", Guid.NewGuid());
        var result = await doctor.GetFromJsonAsync<JsonElement>("/api/doctor/appointments");
        Assert.Single(result.GetProperty("appointments").EnumerateArray());
        Assert.Equal(1, result.GetProperty("statistics").GetProperty("patientCount").GetInt32());
        var empty = await other.GetFromJsonAsync<JsonElement>("/api/doctor/appointments");
        Assert.Empty(empty.GetProperty("appointments").EnumerateArray());
        Assert.Equal(HttpStatusCode.NotFound, (await other.GetAsync("/api/doctor/appointments/1")).StatusCode);
        var own = await doctor.GetFromJsonAsync<JsonElement>("/api/doctor/appointments/1");
        Assert.Equal("CN-APT-TEST", own.GetProperty("appointmentReference").GetString());
        var patientId = own.GetProperty("patientId").GetGuid();
        var access = await doctor.PostAsJsonAsync("/api/doctor/appointments/patient-access", new { patientIds = new[] { patientId, Guid.NewGuid() } });
        Assert.Equal(patientId, Assert.Single((await access.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("patientIds").EnumerateArray()).GetGuid());
    }

    [Theory]
    [InlineData(null, HttpStatusCode.Unauthorized)]
    [InlineData("Patient", HttpStatusCode.Forbidden)]
    [InlineData("Admin", HttpStatusCode.Forbidden)]
    [InlineData("PharmacyStaff", HttpStatusCode.Forbidden)]
    public async Task OtherRolesCannotReadOrWrite(string? role, HttpStatusCode expected)
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(true);
        using var client = factory.Client(role);
        Assert.Equal(expected, (await client.GetAsync("/api/doctor/appointments")).StatusCode);
        Assert.Equal(expected, (await client.GetAsync("/api/doctor/appointments/1")).StatusCode);
        Assert.Equal(expected, (await client.PatchAsJsonAsync("/api/doctor/appointments/1/status", new { status = "Confirmed", expectedStatus = "Booked", expectedUpdatedAtUtc = (string?)null })).StatusCode);
        Assert.Equal(expected, (await client.PostAsJsonAsync("/api/doctor/appointments/patient-access", new { patientIds = new[] { Guid.NewGuid() } })).StatusCode);
    }

    [Fact]
    public async Task InvalidIdentityAndInvalidBatchesAreRejected()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(true); await factory.Seed();
        using var invalid = factory.Client("Doctor", Guid.Empty);
        Assert.Equal(HttpStatusCode.Unauthorized, (await invalid.GetAsync("/api/doctor/appointments")).StatusCode);
        using var client = factory.Client("Doctor", Doctor);
        foreach (var ids in new[] { Array.Empty<Guid>(), new[] { Guid.Empty }, new[] { Doctor, Doctor }, Enumerable.Range(0, 101).Select(_ => Guid.NewGuid()).ToArray() })
            Assert.Equal(HttpStatusCode.BadRequest, (await client.PostAsJsonAsync("/api/doctor/appointments/patient-access", new { patientIds = ids })).StatusCode);
    }

    [Fact]
    public async Task SuccessfulStatusChangeIsAuditedAndStaleAndForeignWritesAreRejected()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(true); await factory.Seed();
        using (var scope = factory.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>(); var row = await db.Appointments.SingleAsync();
            row.AppointmentStartUtc = DateTime.UtcNow.AddMinutes(-30); row.AppointmentEndUtc = DateTime.UtcNow.AddMinutes(-1); await db.SaveChangesAsync();
        }
        using var doctor = factory.Client("Doctor", Doctor); using var foreign = factory.Client("Doctor", Guid.NewGuid());
        var update = new { status = "Confirmed", expectedStatus = "Booked", expectedUpdatedAtUtc = (string?)null };
        Assert.Equal(HttpStatusCode.NotFound, (await foreign.PatchAsJsonAsync("/api/doctor/appointments/1/status", update)).StatusCode);
        var response = await doctor.PatchAsJsonAsync("/api/doctor/appointments/1/status", update);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var confirmation = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Confirmed", confirmation.GetProperty("status").GetString());
        Assert.Equal(HttpStatusCode.Conflict, (await doctor.PatchAsJsonAsync("/api/doctor/appointments/1/status", update)).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await doctor.PatchAsJsonAsync("/api/doctor/appointments/1/status", new { status = "NoShow", expectedStatus = "Confirmed", expectedUpdatedAtUtc = confirmation.GetProperty("updatedAtUtc").GetString() })).StatusCode);
        using var patient = factory.Client("Patient");
        var history = await patient.GetFromJsonAsync<JsonElement>("/api/appointments/1");
        Assert.Equal("NoShow", history.GetProperty("status").GetString());
        Assert.Equal("Previous", history.GetProperty("section").GetString()); Assert.False(history.GetProperty("canPay").GetBoolean());
        using var check = factory.Services.CreateScope();
        var checkDb = check.ServiceProvider.GetRequiredService<AppDbContext>();
        var audits = await checkDb.Database.SqlQueryRaw<int>("SELECT COUNT(*) AS Value FROM AppointmentStatusChanges").SingleAsync();
        Assert.Equal(2, audits);
    }

    [Fact]
    public async Task CurrentPaymentUpdatesAreVisibleAndNotOverwrittenByDoctorProgress()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(true); await factory.Seed();
        using (var scope = factory.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>(); var row = await db.Appointments.SingleAsync(); row.AppointmentStartUtc = DateTime.UtcNow.AddMinutes(-10); row.AppointmentEndUtc = DateTime.UtcNow.AddMinutes(20); await db.SaveChangesAsync();
        }
        using var doctor = factory.Client("Doctor", Doctor); using var patient = factory.Client("Patient");
        Assert.Equal(HttpStatusCode.OK, (await patient.PostAsJsonAsync("/api/appointments/1/payment/method", new { method = "Cash" })).StatusCode);
        Assert.Equal("Pending", (await doctor.GetFromJsonAsync<JsonElement>("/api/doctor/appointments/1")).GetProperty("paymentStatus").GetString());
        using (var scope = factory.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>(); var payment = await db.AppointmentPayments.SingleAsync(); payment.Status = AppointmentIntegration.Api.Models.AppointmentPaymentStatus.Successful; await db.SaveChangesAsync();
        }
        Assert.Equal(HttpStatusCode.OK, (await doctor.PatchAsJsonAsync("/api/doctor/appointments/1/status", new { status = "Completed", expectedStatus = "Booked", expectedUpdatedAtUtc = (string?)null })).StatusCode);
        var final = await doctor.GetFromJsonAsync<JsonElement>("/api/doctor/appointments/1"); Assert.Equal("Successful", final.GetProperty("paymentStatus").GetString());
        Assert.Equal("Completed", final.GetProperty("status").GetString());
    }
}
