namespace AppointmentIntegration.Api.Models;

public sealed class AppointmentCancellation
{
    public int Id { get; set; }
    public int AppointmentId { get; set; }
    public Guid PatientId { get; set; }
    public DateTime CancelledAtUtc { get; set; }
    public string PreviousStatus { get; set; } = "";
    public string? Reason { get; set; }
    public int? PaymentId { get; set; }
    public string? PaymentMethod { get; set; }
    public string? PaymentStatus { get; set; }
    public decimal PaymentAmount { get; set; }
    public string RefundOutcome { get; set; } = "NotRequired";
    public decimal RefundAmount { get; set; }
    public string DecisionMessage { get; set; } = "";
}
