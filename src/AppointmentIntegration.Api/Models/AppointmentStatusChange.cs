namespace AppointmentIntegration.Api.Models;

public sealed class AppointmentStatusChange
{
    public int Id { get; set; }
    public int AppointmentId { get; set; }
    public Guid DoctorId { get; set; }
    public string PreviousStatus { get; set; } = "";
    public string NewStatus { get; set; } = "";
    public DateTime ChangedAtUtc { get; set; }
}
