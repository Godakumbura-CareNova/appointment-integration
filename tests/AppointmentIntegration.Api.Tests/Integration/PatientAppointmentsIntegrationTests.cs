using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Models;
using AppointmentIntegration.Api.DTOs.Appointment;
using AppointmentIntegration.Api.Services.Interfaces;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace AppointmentIntegration.Api.Tests.Integration;

public class PatientAppointmentsIntegrationTests
{
    [Fact]
    public async Task MissingPatientIdentityCannotReadAppointmentInformation()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true);
        using var client = factory.Client("Patient", Guid.Empty);
        Assert.Equal(HttpStatusCode.Unauthorized, (await client.GetAsync("/api/appointments")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await client.GetAsync("/api/appointments/1")).StatusCode);
    }

    [Fact]
    public async Task ServiceFailureReturnsAnErrorWithoutInternalDetails()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true);
        using var broken = factory.WithWebHostBuilder(builder => builder.ConfigureServices(services => services.AddScoped<IPatientAppointmentService, UnavailableService>()));
        using var client = broken.CreateClient();
        client.DefaultRequestHeaders.Add("X-Test-Role", "Patient");
        client.DefaultRequestHeaders.Add("X-Test-Patient", Guid.NewGuid().ToString());
        foreach (var path in new[] { "/api/appointments", "/api/appointments/1" })
        {
            var response = await client.GetAsync(path);
            Assert.Equal(HttpStatusCode.InternalServerError, response.StatusCode);
            var body = await response.Content.ReadAsStringAsync();
            Assert.Contains("Please try again", body); Assert.DoesNotContain("private database details", body);
        }
    }

    private sealed class UnavailableService : IPatientAppointmentService
    {
        public Task<IReadOnlyList<AppointmentSummaryDto>> GetAppointmentsAsync(Guid id, CancellationToken cancellationToken = default) => throw new InvalidOperationException("private database details");
        public Task<AppointmentSummaryDto?> GetAppointmentAsync(Guid id, int appointmentId, CancellationToken cancellationToken = default) => throw new InvalidOperationException("private database details");
    }

    [Fact]
    public async Task PatientCanListAndReadOnlyTheirOwnAppointmentsWithCurrentPayment()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true); await factory.Seed();
        using var patient = factory.Client("Patient"); using var other = factory.Client("Patient", Guid.NewGuid());
        var listResponse = await patient.GetAsync("/api/appointments");
        Assert.Equal(HttpStatusCode.OK, listResponse.StatusCode);
        var list = await listResponse.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("CN-APT-TEST", Assert.Single(list.EnumerateArray()).GetProperty("appointmentReference").GetString());
        Assert.Empty((await other.GetFromJsonAsync<JsonElement>("/api/appointments")).EnumerateArray());
        Assert.Equal(HttpStatusCode.NotFound, (await other.GetAsync("/api/appointments/1")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await patient.GetAsync("/api/appointments/999")).StatusCode);
        var before = await patient.GetFromJsonAsync<JsonElement>("/api/appointments/1");
        Assert.Equal(JsonValueKind.Null, before.GetProperty("paymentMethod").ValueKind);
        await patient.PostAsJsonAsync("/api/appointments/1/payment/method", new { method = "Cash" });
        var after = await patient.GetFromJsonAsync<JsonElement>("/api/appointments/1");
        Assert.Equal("Cash", after.GetProperty("paymentMethod").GetString());
        Assert.Equal("Pending", after.GetProperty("paymentStatus").GetString());
    }

    [Theory]
    [InlineData(null, HttpStatusCode.Unauthorized)]
    [InlineData("Doctor", HttpStatusCode.Forbidden)]
    [InlineData("Admin", HttpStatusCode.Forbidden)]
    [InlineData("PharmacyStaff", HttpStatusCode.Forbidden)]
    public async Task NonPatientsCannotUsePatientAppointmentReads(string? role, HttpStatusCode status)
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true);
        using var client = factory.Client(role);
        Assert.Equal(status, (await client.GetAsync("/api/appointments")).StatusCode);
        Assert.Equal(status, (await client.GetAsync("/api/appointments/1")).StatusCode);
    }

    [Fact]
    public async Task UpdatedAppointmentStatusIsReturnedOnTheNextRequest()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true); await factory.Seed();
        using var patient = factory.Client("Patient");
        using var scope = factory.Services.CreateScope(); var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        var appointment = await db.Appointments.SingleAsync(); appointment.Status = AppointmentStatus.Completed; await db.SaveChangesAsync();
        var result = await patient.GetFromJsonAsync<JsonElement>("/api/appointments/1");
        Assert.Equal("Completed", result.GetProperty("status").GetString());
        Assert.Equal("Previous", result.GetProperty("section").GetString());
        Assert.False(result.GetProperty("canPay").GetBoolean());
    }
}
