using AppointmentIntegration.Api.Services;

namespace AppointmentIntegration.Api.Tests.Unit;

public class AppointmentCancellationPolicyTests
{
    private static readonly DateTime Now = new(2026, 10, 11, 8, 0, 0, DateTimeKind.Utc);
    private static CancellationSnapshot Snapshot(string? method = null, string? payment = null, string status = "Booked", bool pending = false) =>
        new(1, Guid.NewGuid(), status, Now.AddHours(6), Now.AddHours(7), null, method is null ? null : 1, method, payment, 1500m, null, pending, "");

    [Theory]
    [InlineData(null, null, true, "NotRequired")]
    [InlineData("Cash", "Pending", true, "NotRequired")]
    [InlineData("Cash", "Successful", false, "NotRequired")]
    [InlineData("BankTransfer", "AwaitingBankTransferReceipt", true, "NotRequired")]
    [InlineData("BankTransfer", "ReceiptUnderVerification", false, "NotRequired")]
    [InlineData("BankTransfer", "Successful", true, "Eligible")]
    [InlineData("PaymentGateway", "Successful", false, "NotRequired")]
    [InlineData("PaymentGateway", "Failed", true, "NotRequired")]
    [InlineData("PaymentGateway", "AwaitingGatewayPayment", true, "NotRequired")]
    [InlineData("Unknown", "Successful", false, "NotRequired")]
    [InlineData("Cash", "Unknown", false, "NotRequired")]
    [InlineData("Cash", "AwaitingGatewayPayment", false, "NotRequired")]
    public void Payment_rules(string? method, string? status, bool allowed, string outcome)
    {
        var decision = AppointmentCancellationPolicy.Evaluate(Snapshot(method, status), Now);
        Assert.Equal(allowed, decision.Allowed); Assert.Equal(outcome, decision.RefundOutcome);
        if (outcome == "Eligible") Assert.Equal(1500m, decision.RefundAmount);
    }

    [Theory]
    [InlineData(-1, "Eligible", false)]
    [InlineData(0, "Eligible", false)]
    [InlineData(1, "NotEligible", true)]
    public void Six_hour_boundary_is_inclusive(long microseconds, string outcome, bool acknowledge)
    {
        var result = AppointmentCancellationPolicy.Evaluate(Snapshot("BankTransfer", "Successful"), Now.AddTicks(microseconds * 10));
        Assert.True(result.Allowed); Assert.Equal(outcome, result.RefundOutcome); Assert.Equal(acknowledge, result.RequiresNoRefundAcknowledgement);
    }

    [Theory]
    [InlineData("Completed")][InlineData("Cancelled")][InlineData("NoShow")][InlineData("Unknown")]
    public void Terminal_or_unknown_appointment_is_blocked(string status) => Assert.False(AppointmentCancellationPolicy.Evaluate(Snapshot(status: status), Now).Allowed);

    [Fact] public void Confirmed_is_eligible() => Assert.True(AppointmentCancellationPolicy.Evaluate(Snapshot(status: "Confirmed"), Now).Allowed);
    [Fact] public void Exact_start_is_blocked() => Assert.False(AppointmentCancellationPolicy.Evaluate(Snapshot(), Now.AddHours(6)).Allowed);
    [Fact] public void Invalid_time_is_blocked() => Assert.False(AppointmentCancellationPolicy.Evaluate(Snapshot() with { StartUtc = default }, Now).Allowed);
    [Fact] public void Active_checkout_blocks_even_if_payment_method_was_replaced() => Assert.False(AppointmentCancellationPolicy.Evaluate(Snapshot("Cash", "Pending", pending: true), Now).Allowed);
}
