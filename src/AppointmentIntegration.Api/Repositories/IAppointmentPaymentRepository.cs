using AppointmentIntegration.Api.Models;

namespace AppointmentIntegration.Api.Repositories;

public interface IAppointmentPaymentRepository
{
    Task<AppointmentPayment?> GetByAppointmentAsync(
        Guid patientId,
        int appointmentId,
        CancellationToken cancellationToken = default);

    Task<AppointmentPayment?> GetByAppointmentIdAsync(
        int appointmentId,
        CancellationToken cancellationToken = default);

    Task<Appointment?> GetAppointmentAsync(
        Guid patientId,
        int appointmentId,
        CancellationToken cancellationToken = default);

    Task<AppointmentReceipt?> GetLatestReceiptAsync(
        int appointmentPaymentId,
        CancellationToken cancellationToken = default);

    Task<List<AppointmentOnlinePaymentAttempt>> GetOnlineAttemptsAsync(
        int appointmentPaymentId,
        CancellationToken cancellationToken = default);

    Task<AppointmentOnlinePaymentAttempt?> GetOnlineAttemptByGatewayReferenceAsync(
        string gatewayReference,
        CancellationToken cancellationToken = default);

    void Add(AppointmentPayment payment);

    void AddReceipt(AppointmentReceipt receipt);

    void AddOnlineAttempt(
        AppointmentOnlinePaymentAttempt attempt);

    Task SaveChangesAsync(
        CancellationToken cancellationToken = default);
}