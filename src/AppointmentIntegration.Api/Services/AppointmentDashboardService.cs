using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.DTOs.Dashboard;
using AppointmentIntegration.Api.Models;
using Microsoft.EntityFrameworkCore;

namespace AppointmentIntegration.Api.Services;

public sealed class AppointmentDashboardService(AppDbContext db, TimeProvider clock)
{
    public async Task<PatientAppointmentDashboard> GetPatientAsync(Guid patientId, CancellationToken ct)
    {
        var now = clock.GetUtcNow().UtcDateTime;
        var query = db.Appointments.AsNoTracking().Where(a => a.PatientId == patientId && a.AppointmentStartUtc > now
            && (a.Status == AppointmentStatus.Booked || a.Status == AppointmentStatus.Confirmed));
        var count = await query.CountAsync(ct);
        var appointments = await query.OrderBy(a => a.AppointmentStartUtc).ThenBy(a => a.Id).Take(5).ToListAsync(ct);
        var ids = appointments.Select(a => a.Id).ToArray();
        var payments = await db.AppointmentPayments.AsNoTracking().Where(p => p.PatientId == patientId && ids.Contains(p.AppointmentId)).ToListAsync(ct);
        var counts = await db.AppointmentPayments.AsNoTracking().Where(p => p.PatientId == patientId && p.Appointment!.PatientId == patientId)
            .GroupBy(p => p.Status).Select(g => new { Status = g.Key, Count = g.Count() }).ToListAsync(ct);
        return new(count, appointments.Select(a => {
            var payment = payments.FirstOrDefault(p => p.AppointmentId == a.Id);
            return new DashboardAppointment(a.Id, a.AppointmentReference, a.DoctorName, Utc(a.AppointmentStartUtc), a.Status.ToString(), payment?.Method.ToString(), payment?.Status.ToString());
        }).ToArray(), counts.ToDictionary(c => c.Status.ToString(), c => c.Count), now);
    }

    public async Task<StaffAppointmentPaymentDashboard> GetStaffPaymentsAsync(CancellationToken ct)
    {
        var now = clock.GetUtcNow().UtcDateTime;
        var zone = TimeZoneInfo.FindSystemTimeZoneById("Asia/Colombo");
        var local = TimeZoneInfo.ConvertTimeFromUtc(now, zone);
        var day = TimeZoneInfo.ConvertTimeToUtc(DateTime.SpecifyKind(local.Date, DateTimeKind.Unspecified), zone);
        var month = TimeZoneInfo.ConvertTimeToUtc(new DateTime(local.Year, local.Month, 1, 0, 0, 0, DateTimeKind.Unspecified), zone);
        var pending = db.AppointmentPayments.AsNoTracking().Where(p => p.Method == AppointmentPaymentMethod.BankTransfer
            && p.Status == AppointmentPaymentStatus.ReceiptUnderVerification
            && db.AppointmentReceipts.Any(r => r.AppointmentPaymentId == p.Id && r.Status == AppointmentReceiptStatus.PendingVerification));
        var pendingCount = await pending.CountAsync(ct);
        var pendingRows = await pending.Include(p => p.Appointment).OrderBy(p => p.UpdatedAtUtc).ThenBy(p => p.Id).Take(5).ToListAsync(ct);
        var paid = db.AppointmentPayments.AsNoTracking().Where(p => p.Status == AppointmentPaymentStatus.Successful
            && !db.AppointmentPaymentReconciliations.Any(r => r.PaymentId == p.Id));
        var dated = paid.Where(p => p.ConfirmedAtUtc != null && p.ConfirmedAtUtc <= now);
        var today = await dated.Where(p => p.ConfirmedAtUtc >= day).SumAsync(p => (decimal?)p.Amount, ct) ?? 0m;
        var monthly = await dated.Where(p => p.ConfirmedAtUtc >= month).SumAsync(p => (decimal?)p.Amount, ct) ?? 0m;
        var undated = paid.Where(p => p.ConfirmedAtUtc == null);
        var undatedCount = await undated.CountAsync(ct);
        var undatedAmount = await undated.SumAsync(p => (decimal?)p.Amount, ct) ?? 0m;
        var recent = await dated.Include(p => p.Appointment).OrderByDescending(p => p.ConfirmedAtUtc).ThenByDescending(p => p.Id).Take(5).ToListAsync(ct);
        return new(new(pendingCount, pendingRows.Select(ToRow).ToArray()), recent.Select(ToRow).ToArray(),
            new(today, monthly, undatedCount, undatedAmount, "LKR", "Asia/Colombo", now), now);
    }

    private static DateTime Utc(DateTime value) => DateTime.SpecifyKind(value, DateTimeKind.Utc);
    private static AppointmentDashboardPayment ToRow(AppointmentPayment p) => new(p.Id, p.AppointmentId, p.Appointment!.AppointmentReference,
        p.Amount, p.Method.ToString(), p.Status.ToString(), p.ConfirmedAtUtc.HasValue ? Utc(p.ConfirmedAtUtc.Value) : null, Utc(p.UpdatedAtUtc));
}
