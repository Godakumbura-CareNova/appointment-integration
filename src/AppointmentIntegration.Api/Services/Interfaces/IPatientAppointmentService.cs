using AppointmentIntegration.Api.DTOs.Appointment;

namespace AppointmentIntegration.Api.Services.Interfaces;

public interface IPatientAppointmentService
{
    Task<IReadOnlyList<AppointmentSummaryDto>> GetAppointmentsAsync(Guid patientId, CancellationToken cancellationToken = default);
    Task<AppointmentSummaryDto?> GetAppointmentAsync(Guid patientId, int appointmentId, CancellationToken cancellationToken = default);
}
