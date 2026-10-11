namespace AppointmentIntegration.Api.Clients;

public sealed record PatientContactDto(Guid PatientId, string FullName, string? MobileNumber);
public interface IUserAuthClient
{
    Task<IReadOnlyList<PatientContactDto>> GetContactsAsync(IReadOnlyCollection<Guid> patientIds, string bearerToken, CancellationToken ct);
}
