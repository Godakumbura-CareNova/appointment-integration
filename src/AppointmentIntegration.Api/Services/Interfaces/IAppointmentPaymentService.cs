using AppointmentIntegration.Api.DTOs.AppointmentPayment;
using Microsoft.AspNetCore.Http;

namespace AppointmentIntegration.Api.Services.Interfaces;

public interface IAppointmentPaymentService
{
    Task<AppointmentPaymentResponseDto> SelectPaymentMethodAsync(
        Guid patientId,
        int appointmentId,
        SelectAppointmentPaymentMethodDto request,
        CancellationToken cancellationToken = default);

    Task<AppointmentPaymentResponseDto?> GetPaymentAsync(
        Guid patientId,
        int appointmentId,
        CancellationToken cancellationToken = default);

    Task<AppointmentPaymentResponseDto> UploadReceiptAsync(
        Guid patientId,
        int appointmentId,
        IFormFile receipt,
        CancellationToken cancellationToken = default);

    Task<AppointmentPaymentResponseDto> VerifyReceiptAsync(
    Guid staffId,
    int appointmentId,
    AppointmentReceiptVerificationDto request,
    CancellationToken cancellationToken = default);

}