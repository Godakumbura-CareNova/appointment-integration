using System.Net;
using System.Net.Http.Json;

namespace AppointmentIntegration.Api.Clients;

public class DoctorPaymentClient
{
    private readonly HttpClient _httpClient;
    private readonly IHttpContextAccessor _httpContextAccessor;

    public DoctorPaymentClient(
        HttpClient httpClient,
        IHttpContextAccessor httpContextAccessor)
    {
        _httpClient = httpClient;
        _httpContextAccessor = httpContextAccessor;
    }

    public async Task<DoctorProfileResponse?> GetDoctorAsync(
        Guid doctorId,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(
            HttpMethod.Get,
            $"api/doctors/{doctorId}");

        var authorization =
            _httpContextAccessor.HttpContext?
                .Request.Headers.Authorization.ToString();

        if (!string.IsNullOrWhiteSpace(authorization))
        {
            request.Headers.TryAddWithoutValidation(
                "Authorization",
                authorization);
        }

        using var response = await _httpClient.SendAsync(
            request,
            cancellationToken);

        if (response.StatusCode == HttpStatusCode.NotFound)
        {
            return null;
        }

        response.EnsureSuccessStatusCode();

        return await response.Content.ReadFromJsonAsync<DoctorProfileResponse>(
            cancellationToken: cancellationToken);
    }
}

public class DoctorProfileResponse
{
    public Guid DoctorId { get; set; }

    public string FullName { get; set; } = string.Empty;

    public decimal? ConsultationFee { get; set; }

    public DoctorAvailabilityResponse Availability { get; set; } = new();

    public List<DoctorSlotResponse> UpcomingSlots { get; set; } = new();
}

public class DoctorAvailabilityResponse
{
    public bool HasAvailableSlots { get; set; }

    public int AvailableSlotCount { get; set; }

    public DateTime? NextAvailableSlotUtc { get; set; }
}

public class DoctorSlotResponse
{
    public int Id { get; set; }

    public DateTime StartUtc { get; set; }

    public DateTime EndUtc { get; set; }
}