namespace AppointmentIntegration.Api.Models;

public class Appointment
{
    public int Id { get; set; }

    public string AppointmentReference { get; set; } = string.Empty;

    public Guid PatientId { get; set; }

    public Guid DoctorId { get; set; }

    public string DoctorName { get; set; } = string.Empty;

    public int DoctorAvailabilitySlotId { get; set; }

    public DateTime AppointmentStartUtc { get; set; }

    public DateTime AppointmentEndUtc { get; set; }

    public AppointmentStatus Status { get; set; } = AppointmentStatus.Booked;

    public DateTime CreatedAtUtc { get; set; }

    public DateTime? UpdatedAtUtc { get; set; }
}