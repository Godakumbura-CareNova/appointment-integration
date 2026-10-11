namespace AppointmentIntegration.Api.DTOs.Appointment;

public sealed class DoctorAppointmentDto
{
    public int Id { get; set; }
    public string AppointmentReference { get; set; } = "";
    public Guid PatientId { get; set; }
    public string? PatientName { get; set; }
    public string? PatientPhone { get; set; }
    public DateTime AppointmentStartUtc { get; set; }
    public DateTime AppointmentEndUtc { get; set; }
    public string Status { get; set; } = "Unavailable";
    public DateTime? UpdatedAtUtc { get; set; }
    public string? PaymentMethod { get; set; }
    public string? PaymentStatus { get; set; }
    public bool IsToday { get; set; }
    public bool IsUpcoming { get; set; }
    public bool IsCompleted { get; set; }
    public bool IsHistory { get; set; }
    public IReadOnlyList<string> AllowedStatuses { get; set; } = [];
    public bool ContactsUnavailable { get; set; }
}
