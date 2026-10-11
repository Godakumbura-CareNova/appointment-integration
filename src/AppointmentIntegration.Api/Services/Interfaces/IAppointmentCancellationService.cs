using AppointmentIntegration.Api.DTOs.Cancellation;

namespace AppointmentIntegration.Api.Services.Interfaces;

public interface IAppointmentCancellationService
{
    Task<CancellationEligibilityDto?> GetEligibilityAsync(Guid patientId, int appointmentId, CancellationToken ct = default);
    Task<CancellationResponseDto> CancelAsync(Guid patientId, int appointmentId, CancelAppointmentRequestDto request, CancellationToken ct = default);
}
