using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Services.Interfaces;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;

namespace AppointmentIntegration.Api.Services;

public sealed class AppointmentMutationScope(AppDbContext db) : IAppointmentMutationScope
{
    public async Task<IAppointmentMutationLease> BeginAsync(int appointmentId, CancellationToken ct = default)
    {
        // InMemory is used only by existing unit/API fixtures; production must be relational.
        if (db.Database.ProviderName == "Microsoft.EntityFrameworkCore.InMemory") return new Lease(null);
        var transaction = await db.Database.BeginTransactionAsync(ct);
        try
        {
            if (db.Database.ProviderName?.Contains("MySql", StringComparison.OrdinalIgnoreCase) == true)
                await db.Appointments.FromSqlInterpolated($"SELECT * FROM Appointments WHERE Id = {appointmentId} FOR UPDATE").AsNoTracking().ToListAsync(ct);
            else if (db.Database.ProviderName == "Microsoft.EntityFrameworkCore.Sqlite")
                await db.Database.ExecuteSqlInterpolatedAsync($"UPDATE Appointments SET Id = Id WHERE Id = {appointmentId}", ct);
            else throw new NotSupportedException("Appointment mutation requires MySQL or SQLite locking.");
            db.ChangeTracker.Clear();
            return new Lease(transaction);
        }
        catch { await transaction.DisposeAsync(); throw; }
    }

    public void RecordLateGatewayPayment(int appointmentId, int paymentId, int attemptId, DateTime nowUtc) =>
        db.AppointmentPaymentReconciliations.Add(new() { AppointmentId = appointmentId, PaymentId = paymentId, AttemptId = attemptId, CreatedAtUtc = nowUtc });

    private sealed class Lease(IDbContextTransaction? transaction) : IAppointmentMutationLease
    {
        public Task CommitAsync(CancellationToken ct = default) => transaction?.CommitAsync(ct) ?? Task.CompletedTask;
        public ValueTask DisposeAsync() => transaction?.DisposeAsync() ?? ValueTask.CompletedTask;
    }
}
