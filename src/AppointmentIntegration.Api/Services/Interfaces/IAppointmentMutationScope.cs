namespace AppointmentIntegration.Api.Services.Interfaces;

public interface IAppointmentMutationScope
{
    Task<IAppointmentMutationLease> BeginAsync(int appointmentId, CancellationToken ct = default);
    void RecordLateGatewayPayment(int appointmentId, int paymentId, int attemptId, DateTime nowUtc);
}

public interface IAppointmentMutationLease : IAsyncDisposable
{
    Task CommitAsync(CancellationToken ct = default);
}
