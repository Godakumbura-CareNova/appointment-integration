namespace AppointmentIntegration.Api.DTOs.Appointment;

public sealed class UpdateAppointmentStatusDto
{
    public string Status { get; set; } = "";
    public string ExpectedStatus { get; set; } = "";
    public DateTime? ExpectedUpdatedAtUtc { get; set; }
}
