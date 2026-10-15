namespace AppointmentIntegration.Api.DTOs.AppointmentPayment;

public class AppointmentPaymentResponseDto
{
    public int Id { get; set; }

    public int AppointmentId { get; set; }

    public string AppointmentReference { get; set; } = string.Empty;

    public decimal Amount { get; set; }

    public string Method { get; set; } = string.Empty;

    public string Status { get; set; } = string.Empty;

    public DateTime UpdatedAtUtc { get; set; }
    public AppointmentReceiptFeedbackDto? LatestReceipt { get; set; }
}
