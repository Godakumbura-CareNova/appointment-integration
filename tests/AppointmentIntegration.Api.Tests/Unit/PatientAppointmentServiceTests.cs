using AppointmentIntegration.Api.Models;
using AppointmentIntegration.Api.Services;
using AppointmentIntegration.Api.Tests.Support;
using Microsoft.EntityFrameworkCore;

namespace AppointmentIntegration.Api.Tests.Unit;

public class PatientAppointmentServiceTests
{
    private static readonly DateTime Now = new(2026, 10, 11, 8, 0, 0, DateTimeKind.Utc);
    private sealed class FixedClock : TimeProvider { public override DateTimeOffset GetUtcNow() => new(Now); }

    [Theory]
    [InlineData(AppointmentStatus.Booked, 1, "Upcoming", true)]
    [InlineData(AppointmentStatus.Confirmed, -1, "Previous", false)]
    [InlineData(AppointmentStatus.Completed, 1, "Previous", false)]
    [InlineData(AppointmentStatus.Cancelled, 1, "Previous", false)]
    [InlineData((AppointmentStatus)999, 1, "Unavailable", false)]
    public async Task SectionAndActionsRespectTimeAndStoredStatus(AppointmentStatus status, int days, string section, bool canPay)
    {
        using var f = new PaymentFixture(relational: true); var appointment = await f.Db.Appointments.SingleAsync();
        appointment.Status = status; appointment.AppointmentStartUtc = Now.AddDays(days); appointment.AppointmentEndUtc = Now.AddDays(days).AddMinutes(30); await f.Db.SaveChangesAsync();
        var service = new PatientAppointmentService(f.Db, new FixedClock());
        var result = Assert.Single(await service.GetAppointmentsAsync(PaymentFixture.Patient));
        Assert.Equal(section, result.Section); Assert.Equal(canPay, result.CanPay);
        Assert.Equal(status == (AppointmentStatus)999 ? "Unavailable" : status.ToString(), result.Status);
        Assert.Equal(DateTimeKind.Utc, result.AppointmentStartUtc.Kind);
    }

    [Fact]
    public async Task AppointmentEndingNowIsHistoryWithoutChangingItsStatus()
    {
        using var f = new PaymentFixture(relational: true); var appointment = await f.Db.Appointments.SingleAsync();
        appointment.AppointmentStartUtc = Now.AddMinutes(-30); appointment.AppointmentEndUtc = Now; await f.Db.SaveChangesAsync();
        var service = new PatientAppointmentService(f.Db, new FixedClock());
        var result = await service.GetAppointmentAsync(PaymentFixture.Patient, 1);
        Assert.Equal("Previous", result!.Section); Assert.Equal("Booked", result.Status); Assert.False(result.CanPay);
        Assert.Equal(AppointmentStatus.Booked, (await f.Db.Appointments.SingleAsync()).Status);
    }

    [Fact]
    public async Task CurrentConsultationRemainsUpcomingUntilItEnds()
    {
        using var f = new PaymentFixture(relational: true); var appointment = await f.Db.Appointments.SingleAsync();
        appointment.AppointmentStartUtc = Now.AddMinutes(-10); appointment.AppointmentEndUtc = Now.AddMinutes(20); await f.Db.SaveChangesAsync();
        Assert.Equal("Upcoming", (await new PatientAppointmentService(f.Db, new FixedClock()).GetAppointmentAsync(PaymentFixture.Patient, 1))!.Section);
    }

    [Theory]
    [InlineData(AppointmentPaymentStatus.Successful)]
    [InlineData(AppointmentPaymentStatus.ReceiptUnderVerification)]
    public async Task SettledOrUnderReviewPaymentsDoNotOfferAnotherPayment(AppointmentPaymentStatus status)
    {
        using var f = new PaymentFixture(relational: true); await f.Select("BankTransfer");
        (await f.Db.AppointmentPayments.SingleAsync()).Status = status; await f.Db.SaveChangesAsync();
        var result = await new PatientAppointmentService(f.Db, TimeProvider.System).GetAppointmentAsync(PaymentFixture.Patient, 1);
        Assert.Equal("BankTransfer", result!.PaymentMethod); Assert.Equal(status.ToString(), result.PaymentStatus); Assert.False(result.CanPay);
    }

    [Fact]
    public async Task QueryDoesNotExposeAnotherPatientsRecordsOrCreatePayments()
    {
        using var f = new PaymentFixture(relational: true); var service = new PatientAppointmentService(f.Db, new FixedClock()); var other = Guid.NewGuid();
        Assert.Empty(await service.GetAppointmentsAsync(other)); Assert.Null(await service.GetAppointmentAsync(other, 1));
        Assert.Null(await service.GetAppointmentAsync(PaymentFixture.Patient, 999));
        Assert.Null((await service.GetAppointmentAsync(PaymentFixture.Patient, 1))!.PaymentStatus); Assert.Empty(f.Db.AppointmentPayments);
        await Assert.ThrowsAsync<ArgumentException>(() => service.GetAppointmentsAsync(Guid.Empty));
    }
}
