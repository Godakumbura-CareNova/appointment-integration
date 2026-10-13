using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.DTOs.Cancellation;
using AppointmentIntegration.Api.Models;
using AppointmentIntegration.Api.Repositories;
using AppointmentIntegration.Api.Services;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Time.Testing;

namespace AppointmentIntegration.Api.Tests.Integration;

public class AppointmentCancellationPersistenceTests
{
    private sealed class Fixture : IAsyncDisposable
    {
        public readonly SqliteConnection Connection = new("Data Source=:memory:");
        public readonly FakeTimeProvider Clock = new(new DateTimeOffset(2026, 10, 11, 8, 0, 0, TimeSpan.Zero));
        public AppDbContext Db = null!;
        public readonly Guid Patient = Guid.NewGuid();
        public AppointmentCancellationService Service => new(Db, Clock, new AppointmentMutationScope(Db));
        public async Task Seed()
        {
            await Connection.OpenAsync(); Db = new(new DbContextOptionsBuilder<AppDbContext>().UseSqlite(Connection).Options); await Db.Database.EnsureCreatedAsync();
            Db.Appointments.Add(new() { Id = 1, PatientId = Patient, DoctorId = Guid.NewGuid(), AppointmentReference = "CN-1", DoctorName = "Dr Test", DoctorAvailabilitySlotId = 10,
                AppointmentStartUtc = Clock.GetUtcNow().UtcDateTime.AddHours(6), AppointmentEndUtc = Clock.GetUtcNow().UtcDateTime.AddHours(7) });
            Db.AppointmentPayments.Add(new() { Id = 1, AppointmentId = 1, PatientId = Patient, Method = AppointmentPaymentMethod.BankTransfer, Status = AppointmentPaymentStatus.Successful, Amount = 2000, UpdatedAtUtc = Clock.GetUtcNow().UtcDateTime });
            await Db.SaveChangesAsync(); Db.ChangeTracker.Clear();
        }
        public async ValueTask DisposeAsync() { if (Db is not null) await Db.DisposeAsync(); await Connection.DisposeAsync(); }
    }

    [Fact] public async Task Crossing_refund_boundary_requires_reconfirmation_even_without_row_changes()
    {
        await using var fixture = new Fixture(); await fixture.Seed(); var before = await fixture.Service.GetEligibilityAsync(fixture.Patient, 1);
        Assert.Equal("Eligible", before!.RefundOutcome); fixture.Clock.Advance(TimeSpan.FromTicks(10));
        await Assert.ThrowsAsync<DbUpdateConcurrencyException>(() => fixture.Service.CancelAsync(fixture.Patient, 1, new() { ExpectedVersion = before.Version, AcknowledgeNoRefund = true }));
        Assert.Empty(await fixture.Db.AppointmentCancellations.ToListAsync()); Assert.Equal(AppointmentStatus.Booked, (await fixture.Db.Appointments.AsNoTracking().SingleAsync()).Status);
    }
    [Fact] public async Task Refund_insert_failure_rolls_back_appointment_and_cancellation()
    {
        await using var fixture = new Fixture(); await fixture.Seed(); var eligibility = await fixture.Service.GetEligibilityAsync(fixture.Patient, 1);
        await fixture.Db.Database.ExecuteSqlRawAsync("CREATE TRIGGER FailRefund BEFORE INSERT ON RefundRecords BEGIN SELECT RAISE(ABORT, 'refund failure'); END;");
        await Assert.ThrowsAsync<DbUpdateException>(() => fixture.Service.CancelAsync(fixture.Patient, 1, new() { ExpectedVersion = eligibility!.Version }));
        fixture.Db.ChangeTracker.Clear(); Assert.Equal(AppointmentStatus.Booked, (await fixture.Db.Appointments.SingleAsync()).Status);
        Assert.Empty(await fixture.Db.AppointmentCancellations.ToListAsync()); Assert.Empty(await fixture.Db.RefundRecords.ToListAsync());
    }
    [Fact] public async Task Payment_change_invalidates_eligibility_without_appointment_timestamp_change()
    {
        await using var fixture = new Fixture(); await fixture.Seed(); var eligibility = await fixture.Service.GetEligibilityAsync(fixture.Patient, 1);
        await fixture.Db.Database.ExecuteSqlRawAsync("UPDATE AppointmentPayments SET Amount = 3000 WHERE Id = 1");
        await Assert.ThrowsAsync<DbUpdateConcurrencyException>(() => fixture.Service.CancelAsync(fixture.Patient, 1, new() { ExpectedVersion = eligibility!.Version }));
        Assert.Empty(await fixture.Db.RefundRecords.ToListAsync());
    }
    [Fact] public async Task Cancelled_slot_remains_reserved_without_deleting_history()
    {
        await using var fixture = new Fixture(); await fixture.Seed(); var eligibility = await fixture.Service.GetEligibilityAsync(fixture.Patient, 1);
        await fixture.Service.CancelAsync(fixture.Patient, 1, new() { ExpectedVersion = eligibility!.Version });
        Assert.True(await new AppointmentRepository(fixture.Db).SlotAlreadyBookedAsync(10)); Assert.Equal(1, await fixture.Db.Appointments.CountAsync());
    }
    [Fact] public async Task Unknown_stored_payment_status_returns_blocked_eligibility_instead_of_crashing()
    {
        await using var fixture = new Fixture(); await fixture.Seed(); await fixture.Db.Database.ExecuteSqlRawAsync("UPDATE AppointmentPayments SET Status = 'FutureStatus' WHERE Id = 1");
        var eligibility = await fixture.Service.GetEligibilityAsync(fixture.Patient, 1); Assert.False(eligibility!.Allowed);
    }
    [Fact] public async Task Successful_gateway_attempt_with_failed_payment_fails_closed()
    {
        await using var fixture = new Fixture(); await fixture.Seed();
        await fixture.Db.Database.ExecuteSqlRawAsync("UPDATE AppointmentPayments SET Method = 'PaymentGateway', Status = 'Failed' WHERE Id = 1");
        fixture.Db.AppointmentOnlinePaymentAttempts.Add(new() { AppointmentId = 1, AppointmentPaymentId = 1, PatientId = fixture.Patient, GatewayReference = "CN-1-1", Currency = "LKR", Amount = 2000, Status = AppointmentOnlinePaymentAttemptStatus.Succeeded }); await fixture.Db.SaveChangesAsync();
        Assert.False((await fixture.Service.GetEligibilityAsync(fixture.Patient, 1))!.Allowed);
    }
}
