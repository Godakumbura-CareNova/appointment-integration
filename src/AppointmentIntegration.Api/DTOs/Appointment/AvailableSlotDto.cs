namespace AppointmentIntegration.Api.DTOs.Appointment;

public class AvailableSlotDto
{
    public int Id { get; set; }

    public DateTime StartUtc { get; set; }

    public DateTime EndUtc { get; set; }
}