using System.Net.Http.Headers;
using System.Net.Http.Json;

namespace AppointmentIntegration.Api.Clients;

public sealed class UserAuthClient(HttpClient http) : IUserAuthClient
{
    public async Task<IReadOnlyList<PatientContactDto>> GetContactsAsync(IReadOnlyCollection<Guid> patientIds, string bearerToken, CancellationToken ct)
    {
        if (http.BaseAddress is null || !AuthenticationHeaderValue.TryParse(bearerToken, out var authorization) || authorization.Scheme != "Bearer" || string.IsNullOrWhiteSpace(authorization.Parameter))
            throw new HttpRequestException("Patient contacts are unavailable.");
        using var request = new HttpRequestMessage(HttpMethod.Post, "api/doctor/patient-contacts") { Content = JsonContent.Create(new { patientIds }) };
        request.Headers.Authorization = authorization;
        using var response = await http.SendAsync(request, ct);
        if (response.StatusCode != System.Net.HttpStatusCode.OK) throw new HttpRequestException("Patient contacts are unavailable.");
        var contacts = await response.Content.ReadFromJsonAsync<PatientContactDto[]>(cancellationToken: ct);
        if (contacts is null || contacts.Length > patientIds.Count || contacts.Any(x => x is null || !patientIds.Contains(x.PatientId) || string.IsNullOrWhiteSpace(x.FullName)) || contacts.Select(x => x.PatientId).Distinct().Count() != contacts.Length)
            throw new HttpRequestException("Invalid patient contact response.");
        return contacts;
    }
}
