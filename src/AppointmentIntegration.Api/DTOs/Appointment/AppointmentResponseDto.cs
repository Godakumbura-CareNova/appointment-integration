namespace AppointmentIntegration.Api.DTOs.Appointment;

public class AppointmentResponseDto
{
    public int Id { get; set; }

    public string AppointmentReference { get; set; } = string.Empty;

    public Guid PatientId { get; set; }

    public Guid DoctorId { get; set; }

    public string DoctorName { get; set; } = string.Empty;

    public int SlotId { get; set; }

    public DateTime AppointmentStartUtc { get; set; }

    public DateTime AppointmentEndUtc { get; set; }

    public string Status { get; set; } = string.Empty;

    public DateTime CreatedAtUtc { get; set; }
}