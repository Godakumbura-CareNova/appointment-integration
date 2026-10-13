using AppointmentIntegration.Api.DTOs.Appointment;

namespace AppointmentIntegration.Api.Services.Interfaces;

public interface IDoctorAppointmentService
{
    Task<DoctorAppointmentListDto> GetAppointmentsAsync(Guid doctorId, CancellationToken ct = default);
    Task<DoctorAppointmentDto?> GetAppointmentAsync(Guid doctorId, int id, CancellationToken ct = default);
    Task<IReadOnlyList<Guid>> GetAssignedPatientIdsAsync(Guid doctorId, IReadOnlyCollection<Guid> patientIds, CancellationToken ct = default);
    Task<AppointmentStatusResultDto?> UpdateStatusAsync(Guid doctorId, int id, UpdateAppointmentStatusDto request, CancellationToken ct = default);
}
