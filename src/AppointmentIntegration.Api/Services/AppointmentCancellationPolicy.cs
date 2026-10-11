namespace AppointmentIntegration.Api.Services;

public sealed record CancellationSnapshot(int AppointmentId, Guid PatientId, string Status, DateTime StartUtc, DateTime EndUtc,
    DateTime? UpdatedAtUtc, int? PaymentId, string? PaymentMethod, string? PaymentStatus, decimal Amount, DateTime? PaymentUpdatedAtUtc,
    bool HasPendingCheckout, string AttemptsVersion, bool HasSuccessfulCheckout = false);

public sealed record CancellationDecision(bool Allowed, string ReasonCode, string Message, string RefundOutcome = "NotRequired",
    decimal RefundAmount = 0, bool RequiresNoRefundAcknowledgement = false);

public static class AppointmentCancellationPolicy
{
    public static CancellationDecision Evaluate(CancellationSnapshot snapshot, DateTime nowUtc)
    {
        static CancellationDecision Deny(string code, string message) => new(false, code, message);
        if (snapshot.Status is not ("Booked" or "Confirmed")) return Deny("AppointmentNotEligible", "This appointment cannot be cancelled in its current status.");
        if (snapshot.StartUtc == default || snapshot.EndUtc <= snapshot.StartUtc) return Deny("InformationUnavailable", "Appointment time is unavailable. Refresh or contact the pharmacy.");
        if (nowUtc >= snapshot.StartUtc) return Deny("AppointmentStarted", "Appointments cannot be cancelled once their scheduled start time has been reached.");
        if (snapshot.HasPendingCheckout) return Deny("CheckoutInProgress", "An online checkout is still in progress. Wait for its outcome before cancelling.");
        var method = snapshot.PaymentMethod; var status = snapshot.PaymentStatus;
        if (snapshot.HasSuccessfulCheckout && (method != "PaymentGateway" || status != "Successful"))
            return Deny("PaymentNeedsReview", "A successful online payment is recorded. Cancellation is unavailable; contact the pharmacy to review payment information.");
        if (snapshot.PaymentId is null)
            return method is null && status is null ? new(true, "Unpaid", "No refund is required because payment has not been made.") : Deny("InformationUnavailable", "Payment information is inconsistent. Refresh or contact the pharmacy.");
        if (snapshot.Amount <= 0) return Deny("InformationUnavailable", "Payment information is unavailable. Refresh or contact the pharmacy.");
        switch (method)
        {
            case "Cash" when status == "Successful": return Deny("CashAlreadyPaid", "A cash appointment that has already been paid cannot be cancelled here.");
            case "Cash" when status == "Pending": return new(true, "Unpaid", "No refund is required because cash payment has not been made.");
            case "BankTransfer" when status == "ReceiptUnderVerification": return Deny("ReceiptUnderVerification", "Your bank transfer receipt is being verified. Cancellation is available after verification is resolved.");
            case "BankTransfer" when status is "AwaitingBankTransferReceipt" or "Pending" or "Failed": return new(true, "Unpaid", "No verified payment has been recorded, so no refund is required.");
            case "BankTransfer" when status == "Successful":
                return snapshot.StartUtc - nowUtc >= TimeSpan.FromHours(6)
                    ? new(true, "RefundEligible", "Eligible for a refund, awaiting manual processing by pharmacy staff.", "Eligible", snapshot.Amount)
                    : new(true, "RefundNotEligible", "Less than 6 hours remain. You may cancel, but no refund is available.", "NotEligible", 0, true);
            case "PaymentGateway" when status == "Successful": return Deny("GatewayAlreadyPaid", "Patient cancellation and refunds are not available after successful online payment.");
            case "PaymentGateway" when status is "AwaitingGatewayPayment" or "Failed": return new(true, "Unpaid", "No successful online payment is recorded. No refund is required.");
            default: return Deny("InformationUnavailable", "Payment information is unavailable or inconsistent. Refresh or contact the pharmacy.");
        }
    }
}
