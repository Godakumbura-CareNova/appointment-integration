using AppointmentIntegration.Api.DTOs.AppointmentPayment;

namespace AppointmentIntegration.Api.Services.Interfaces;

public interface IAppointmentOnlinePaymentService
{
    Task<AppointmentOnlinePaymentSessionDto> StartAsync(
        Guid patientId,
        int appointmentId,
        StartAppointmentOnlinePaymentDto request,
        string? origin,
        CancellationToken cancellationToken = default);

    Task<AppointmentOnlinePaymentResultDto> GetResultAsync(
        Guid patientId,
        int appointmentId,
        int attemptId,
        CancellationToken cancellationToken = default);

    Task<AppointmentOnlinePaymentResultDto> CancelAsync(
        Guid patientId,
        int appointmentId,
        int attemptId,
        CancellationToken cancellationToken = default);

    Task<bool> HandleNotificationAsync(
        IReadOnlyDictionary<string, string> form,
        CancellationToken cancellationToken = default);
}