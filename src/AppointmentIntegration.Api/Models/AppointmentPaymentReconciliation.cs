namespace AppointmentIntegration.Api.Models;

public sealed class AppointmentPaymentReconciliation
{
    public int Id { get; set; }
    public int AppointmentId { get; set; }
    public int PaymentId { get; set; }
    public int AttemptId { get; set; }
    public DateTime CreatedAtUtc { get; set; }
    public string Reason { get; set; } = "LateGatewayPaymentAfterCancellation";
    public string Status { get; set; } = "PendingManualReview";
}
