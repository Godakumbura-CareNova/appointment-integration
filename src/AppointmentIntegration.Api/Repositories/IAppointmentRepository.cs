using AppointmentIntegration.Api.Models;

namespace AppointmentIntegration.Api.Repositories;

public interface IAppointmentRepository
{
    Task<bool> SlotAlreadyBookedAsync(
        int slotId,
        CancellationToken cancellationToken = default);

    Task AddAsync(
        Appointment appointment,
        CancellationToken cancellationToken = default);

    Task SaveChangesAsync(
        CancellationToken cancellationToken = default);
}