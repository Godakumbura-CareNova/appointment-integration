namespace AppointmentIntegration.Api.DTOs.Appointment;

public sealed class AppointmentSummaryDto
{
    public int Id { get; init; }
    public string AppointmentReference { get; init; } = string.Empty;
    public string DoctorName { get; init; } = string.Empty;
    public DateTime AppointmentStartUtc { get; init; }
    public DateTime AppointmentEndUtc { get; init; }
    public string Status { get; init; } = "Unavailable";
    public string Section { get; init; } = "Unavailable";
    public string? PaymentMethod { get; init; }
    public string? PaymentStatus { get; init; }
    public bool CanPay { get; init; }
}
