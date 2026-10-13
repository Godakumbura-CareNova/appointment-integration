using AppointmentIntegration.Api.DTOs.Appointment;

namespace AppointmentIntegration.Api.Services.Interfaces;

public interface IAppointmentBookingService
{
    Task<AppointmentResponseDto> BookAsync(
        Guid patientId,
        BookAppointmentRequestDto request,
        CancellationToken cancellationToken = default);
}