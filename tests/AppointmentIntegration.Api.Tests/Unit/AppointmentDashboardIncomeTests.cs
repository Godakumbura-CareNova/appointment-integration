using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Models;
using AppointmentIntegration.Api.Services;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Time.Testing;

namespace AppointmentIntegration.Api.Tests.Unit;

public class AppointmentDashboardIncomeTests
{
    [Fact]
    public async Task Income_UsesConfirmationDate_ExcludesFailedFutureAndReconciledFunds_AndReportsLegacy()
    {
        await using var db = new AppDbContext(new DbContextOptionsBuilder<AppDbContext>().UseInMemoryDatabase(Guid.NewGuid().ToString()).Options);
        var now = new DateTime(2026, 11, 1, 1, 0, 0, DateTimeKind.Utc);
        var times = new DateTime?[] { new(2026, 10, 31, 18, 29, 59, DateTimeKind.Utc), new(2026, 10, 31, 18, 30, 0, DateTimeKind.Utc), null, now.AddDays(1), now, now };
        for (var i = 0; i < times.Length; i++)
        {
            var appointment = new Appointment { Id = i + 1, AppointmentReference = $"APT-{i}", PatientId = Guid.NewGuid(), DoctorAvailabilitySlotId = i + 1 };
            db.AppointmentPayments.Add(new() { Id = i + 1, Appointment = appointment, PatientId = appointment.PatientId, Amount = 100,
                Status = i == 4 ? AppointmentPaymentStatus.Failed : AppointmentPaymentStatus.Successful, Method = AppointmentPaymentMethod.PaymentGateway,
                ConfirmedAtUtc = times[i], CreatedAtUtc = now, UpdatedAtUtc = now });
        }
        db.AppointmentPaymentReconciliations.Add(new() { AppointmentId = 6, PaymentId = 6, AttemptId = 10, CreatedAtUtc = now });
        await db.SaveChangesAsync();
        var result = await new AppointmentDashboardService(db, new FakeTimeProvider(new DateTimeOffset(now))).GetStaffPaymentsAsync(default);
        Assert.Equal(100m, result.Income.TodayAmount);
        Assert.Equal(100m, result.Income.MonthAmount);
        Assert.Equal(1, result.Income.UndatedSuccessfulCount);
        Assert.Equal(100m, result.Income.UndatedSuccessfulAmount);
    }
}
