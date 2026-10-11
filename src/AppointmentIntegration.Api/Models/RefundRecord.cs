namespace AppointmentIntegration.Api.Models;

public sealed class RefundRecord
{
    public int Id { get; set; }
    public int CancellationId { get; set; }
    public AppointmentCancellation Cancellation { get; set; } = null!;
    public decimal Amount { get; set; }
    public string Currency { get; set; } = "LKR";
    public string Status { get; set; } = "PendingManualProcessing";
    public DateTime CreatedAtUtc { get; set; }
}
