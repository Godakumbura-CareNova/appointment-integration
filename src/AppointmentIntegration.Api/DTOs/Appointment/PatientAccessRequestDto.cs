namespace AppointmentIntegration.Api.DTOs.Appointment;

public sealed class PatientAccessRequestDto
{
    public Guid[]? PatientIds { get; set; }
    public bool IsValid => PatientIds is { Length: > 0 and <= 100 } && PatientIds.All(id => id != Guid.Empty) && PatientIds.Distinct().Count() == PatientIds.Length;
}
