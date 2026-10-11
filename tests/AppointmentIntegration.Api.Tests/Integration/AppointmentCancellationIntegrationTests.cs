using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Models;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using AppointmentIntegration.Api.Tests.Support;

namespace AppointmentIntegration.Api.Tests.Integration;

public class AppointmentCancellationIntegrationTests
{
    private const string Route = "/api/patient/appointments/1/cancellation";
    private static async Task Prepare(AppointmentPaymentsIntegrationTests.PaymentApiFactory factory, string? method = null, string? status = null, double hours = 8)
    {
        await factory.Seed(); using var scope = factory.Services.CreateScope(); var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        var appointment = await db.Appointments.SingleAsync(); appointment.AppointmentStartUtc = DateTime.UtcNow.AddHours(hours); appointment.AppointmentEndUtc = appointment.AppointmentStartUtc.AddHours(1);
        if (method is not null) db.AppointmentPayments.Add(new() { AppointmentId = 1, PatientId = appointment.PatientId, Amount = 1500,
            Method = Enum.Parse<AppointmentPaymentMethod>(method), Status = Enum.Parse<AppointmentPaymentStatus>(status!), CreatedAtUtc = DateTime.UtcNow, UpdatedAtUtc = DateTime.UtcNow });
        await db.SaveChangesAsync();
    }
    private static async Task<HttpResponseMessage> Cancel(HttpClient client, bool ack = false, string? version = null) =>
        await client.PostAsJsonAsync(Route, new { expectedVersion = version ?? (await client.GetFromJsonAsync<JsonElement>(Route)).GetProperty("version").GetString(), acknowledgeNoRefund = ack, reason = "Plans changed" });

    [Theory]
    [InlineData(null, null, 8, "NotRequired")]
    [InlineData("Cash", "Pending", 8, "NotRequired")]
    [InlineData("BankTransfer", "Successful", 8, "Eligible")]
    [InlineData("BankTransfer", "Successful", 2, "NotEligible")]
    public async Task Cancellation_persists_refund_decision_and_repeat_is_idempotent(string? method, string? payment, double hours, string outcome)
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true); await Prepare(factory, method, payment, hours); using var client = factory.Client("Patient");
        var response = await Cancel(client, ack: true); Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var result = await response.Content.ReadFromJsonAsync<JsonElement>(); Assert.Equal("Cancelled", result.GetProperty("status").GetString()); Assert.Equal(outcome, result.GetProperty("refundOutcome").GetString());
        Assert.Equal(HttpStatusCode.OK, (await Cancel(client, ack: true)).StatusCode);
        using var scope = factory.Services.CreateScope(); var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        Assert.Equal(AppointmentStatus.Cancelled, (await db.Appointments.SingleAsync()).Status);
        Assert.Equal(1, await db.Set<AppointmentCancellation>().CountAsync()); Assert.Equal(outcome == "Eligible" ? 1 : 0, await db.Set<RefundRecord>().CountAsync());
        if (payment == "Successful") Assert.Equal(AppointmentPaymentStatus.Successful, (await db.AppointmentPayments.SingleAsync()).Status);
        var reload = await client.GetFromJsonAsync<JsonElement>(Route); Assert.Equal(outcome, reload.GetProperty("cancellation").GetProperty("refundOutcome").GetString());
        Assert.Equal("Previous", (await client.GetFromJsonAsync<JsonElement>("/api/appointments/1")).GetProperty("section").GetString());
        Assert.Equal(HttpStatusCode.Conflict, (await client.PostAsJsonAsync("/api/appointments/1/payment/method", new { method = "Cash" })).StatusCode);
    }
    [Theory]
    [InlineData("Cash", "Successful")][InlineData("BankTransfer", "ReceiptUnderVerification")][InlineData("PaymentGateway", "Successful")]
    public async Task Restricted_payment_does_not_cancel(string method, string status)
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true); await Prepare(factory, method, status); using var client = factory.Client("Patient");
        Assert.False((await client.GetFromJsonAsync<JsonElement>(Route)).GetProperty("allowed").GetBoolean()); Assert.Equal(HttpStatusCode.BadRequest, (await Cancel(client)).StatusCode);
    }
    [Theory]
    [InlineData(null, HttpStatusCode.Unauthorized)][InlineData("Doctor", HttpStatusCode.Forbidden)][InlineData("Admin", HttpStatusCode.Forbidden)]
    public async Task Only_patient_can_cancel(string? role, HttpStatusCode expected)
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true); await Prepare(factory); using var client = factory.Client(role);
        Assert.Equal(expected, (await client.GetAsync(Route)).StatusCode); Assert.Equal(expected, (await client.PostAsJsonAsync(Route, new { expectedVersion = new string('a', 64) })).StatusCode);
    }
    [Fact] public async Task Foreign_patient_and_invalid_identity_are_denied()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true); await Prepare(factory);
        using var other = factory.Client("Patient", Guid.NewGuid()); using var invalid = factory.Client("Patient", Guid.Empty);
        Assert.Equal(HttpStatusCode.NotFound, (await other.GetAsync(Route)).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await Cancel(other, version: new string('a', 64))).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await invalid.GetAsync(Route)).StatusCode);
    }
    [Fact] public async Task Stale_eligibility_and_missing_no_refund_acknowledgement_are_rejected()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true); await Prepare(factory, "BankTransfer", "Successful", 2); using var client = factory.Client("Patient");
        Assert.Equal(HttpStatusCode.BadRequest, (await Cancel(client)).StatusCode);
        Assert.Equal(HttpStatusCode.Conflict, (await Cancel(client, ack: true, version: new string('a', 64))).StatusCode);
    }

    [Fact] public async Task Active_checkout_blocks_cancellation_and_cancelled_appointment_cannot_start_checkout()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true); await Prepare(factory, "PaymentGateway", "AwaitingGatewayPayment"); using var patient = factory.Client("Patient");
        var started = await patient.PostAsJsonAsync("/api/appointments/1/payment/online/start", PaymentFixture.Billing()); Assert.Equal(HttpStatusCode.OK, started.StatusCode);
        Assert.False((await patient.GetFromJsonAsync<JsonElement>(Route)).GetProperty("allowed").GetBoolean());
        var session = await started.Content.ReadFromJsonAsync<JsonElement>();
        await patient.PostAsync($"/api/appointments/1/payment/online/{session.GetProperty("attemptId").GetInt32()}/cancel", null);
        Assert.Equal(HttpStatusCode.OK, (await Cancel(patient)).StatusCode);
        Assert.Equal(HttpStatusCode.Conflict, (await patient.PostAsJsonAsync("/api/appointments/1/payment/online/start", PaymentFixture.Billing())).StatusCode);
    }

    [Fact] public async Task Late_gateway_success_is_preserved_and_recorded_once_for_manual_review()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true); await Prepare(factory, "PaymentGateway", "AwaitingGatewayPayment"); using var patient = factory.Client("Patient"); using var gateway = factory.Client();
        var session = await (await patient.PostAsJsonAsync("/api/appointments/1/payment/online/start", PaymentFixture.Billing())).Content.ReadFromJsonAsync<JsonElement>();
        await patient.PostAsync($"/api/appointments/1/payment/online/{session.GetProperty("attemptId").GetInt32()}/cancel", null);
        Assert.Equal(HttpStatusCode.OK, (await Cancel(patient)).StatusCode);
        using var fixture = new PaymentFixture(); var notification = fixture.Notification(session.GetProperty("gatewayOrderId").GetString()!, amount: "1500.00");
        for (var i = 0; i < 2; i++) Assert.Equal(HttpStatusCode.OK, (await gateway.PostAsync("/api/appointment-payments/payhere/notify", new FormUrlEncodedContent(notification))).StatusCode);
        using var scope = factory.Services.CreateScope(); var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        Assert.Equal(AppointmentPaymentStatus.Successful, (await db.AppointmentPayments.SingleAsync()).Status);
        Assert.Equal(AppointmentStatus.Cancelled, (await db.Appointments.SingleAsync()).Status);
        Assert.Equal(1, await db.AppointmentPaymentReconciliations.CountAsync()); Assert.Empty(await db.RefundRecords.ToListAsync());
    }

    [Fact] public async Task Late_gateway_success_after_method_replacement_keeps_gateway_evidence_without_marking_cash_paid()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true); await Prepare(factory, "PaymentGateway", "AwaitingGatewayPayment"); using var patient = factory.Client("Patient"); using var gateway = factory.Client();
        var session = await (await patient.PostAsJsonAsync("/api/appointments/1/payment/online/start", PaymentFixture.Billing())).Content.ReadFromJsonAsync<JsonElement>();
        await patient.PostAsync($"/api/appointments/1/payment/online/{session.GetProperty("attemptId").GetInt32()}/cancel", null);
        Assert.Equal(HttpStatusCode.OK, (await patient.PostAsJsonAsync("/api/appointments/1/payment/method", new { method = "Cash" })).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await Cancel(patient)).StatusCode);
        using var fixture = new PaymentFixture(); var notification = fixture.Notification(session.GetProperty("gatewayOrderId").GetString()!, amount: "1500.00");
        for (var i = 0; i < 2; i++) Assert.Equal(HttpStatusCode.OK, (await gateway.PostAsync("/api/appointment-payments/payhere/notify", new FormUrlEncodedContent(notification))).StatusCode);
        using var scope = factory.Services.CreateScope(); var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        Assert.Equal(AppointmentOnlinePaymentAttemptStatus.Succeeded, (await db.AppointmentOnlinePaymentAttempts.SingleAsync()).Status);
        Assert.Equal(AppointmentPaymentMethod.Cash, (await db.AppointmentPayments.SingleAsync()).Method); Assert.Equal(AppointmentPaymentStatus.Pending, (await db.AppointmentPayments.SingleAsync()).Status);
        Assert.Equal(1, await db.AppointmentPaymentReconciliations.CountAsync());
    }
    [Fact] public async Task Cancelling_another_checkout_cannot_downgrade_a_successful_gateway_payment()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(relational: true); await Prepare(factory, "PaymentGateway", "AwaitingGatewayPayment"); using var patient = factory.Client("Patient"); using var gateway = factory.Client();
        var first = await (await patient.PostAsJsonAsync("/api/appointments/1/payment/online/start", PaymentFixture.Billing())).Content.ReadFromJsonAsync<JsonElement>();
        var second = await (await patient.PostAsJsonAsync("/api/appointments/1/payment/online/start", PaymentFixture.Billing())).Content.ReadFromJsonAsync<JsonElement>();
        using var fixture = new PaymentFixture(); await gateway.PostAsync("/api/appointment-payments/payhere/notify", new FormUrlEncodedContent(fixture.Notification(first.GetProperty("gatewayOrderId").GetString()!, amount: "1500.00")));
        await patient.PostAsync($"/api/appointments/1/payment/online/{second.GetProperty("attemptId").GetInt32()}/cancel", null);
        Assert.Equal("Successful", (await patient.GetFromJsonAsync<JsonElement>("/api/appointments/1/payment")).GetProperty("status").GetString());
        Assert.False((await patient.GetFromJsonAsync<JsonElement>(Route)).GetProperty("allowed").GetBoolean());
    }
}
