namespace AppointmentIntegration.Api.DTOs.Appointment;

public class BookAppointmentRequestDto
{
    public Guid DoctorId { get; set; }

    public int SlotId { get; set; }
}