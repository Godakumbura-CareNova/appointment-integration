using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Clients;
using AppointmentIntegration.Api.DTOs.Appointment;
using AppointmentIntegration.Api.Exceptions;
using AppointmentIntegration.Api.Models;
using AppointmentIntegration.Api.Services.Interfaces;
using Microsoft.EntityFrameworkCore;

namespace AppointmentIntegration.Api.Services;

public sealed class DoctorAppointmentService(AppDbContext db, TimeProvider clock, IUserAuthClient contacts, IHttpContextAccessor context, ILogger<DoctorAppointmentService> logger, IAppointmentMutationScope? mutations = null) : IDoctorAppointmentService
{
    public async Task<DoctorAppointmentListDto> GetAppointmentsAsync(Guid doctorId, CancellationToken ct = default)
    {
        var rows = await Query(doctorId).OrderBy(x => x.AppointmentStartUtc).ThenBy(x => x.Id).ToListAsync(ct);
        var now = clock.GetUtcNow().UtcDateTime;
        foreach (var row in rows) Present(row, now);
        await Enrich(rows, ct);
        return new(rows, new(rows.Count(x => x.IsToday), rows.Count(x => x.IsUpcoming), rows.Count(x => x.IsCompleted), rows.Select(x => x.PatientId).Distinct().Count()), rows.Any(x => x.ContactsUnavailable));
    }

    public async Task<DoctorAppointmentDto?> GetAppointmentAsync(Guid doctorId, int id, CancellationToken ct = default)
    {
        var row = await Query(doctorId).SingleOrDefaultAsync(x => x.Id == id, ct);
        if (row is not null) { Present(row, clock.GetUtcNow().UtcDateTime); await Enrich([row], ct); }
        return row;
    }

    private async Task Enrich(IReadOnlyList<DoctorAppointmentDto> rows, CancellationToken ct)
    {
        var token = context.HttpContext?.Request.Headers.Authorization.ToString() ?? "";
        foreach (var batch in rows.Select(x => x.PatientId).Distinct().Chunk(100))
        {
            try
            {
                var found = (await contacts.GetContactsAsync(batch, token, ct)).ToDictionary(x => x.PatientId);
                foreach (var row in rows.Where(x => found.ContainsKey(x.PatientId)))
                {
                    var contact = found[row.PatientId]; row.PatientName = contact.FullName; row.PatientPhone = contact.MobileNumber; row.ContactsUnavailable = false;
                }
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
            catch (Exception ex) { logger.LogWarning("Patient contacts unavailable ({FailureType})", ex.GetType().Name); }
        }
    }

    public async Task<IReadOnlyList<Guid>> GetAssignedPatientIdsAsync(Guid doctorId, IReadOnlyCollection<Guid> patientIds, CancellationToken ct = default) =>
        await db.Appointments.AsNoTracking().Where(x => x.DoctorId == doctorId && patientIds.Contains(x.PatientId)).Select(x => x.PatientId).Distinct().ToListAsync(ct);

    private IQueryable<DoctorAppointmentDto> Query(Guid doctorId) =>
        from a in db.Appointments.AsNoTracking()
        where a.DoctorId == doctorId
        join payment in db.AppointmentPayments.AsNoTracking() on new { AppointmentId = a.Id, a.PatientId } equals new { payment.AppointmentId, payment.PatientId } into payments
        from p in payments.DefaultIfEmpty()
        select new DoctorAppointmentDto {
            Id = a.Id, AppointmentReference = a.AppointmentReference, PatientId = a.PatientId,
            AppointmentStartUtc = a.AppointmentStartUtc, AppointmentEndUtc = a.AppointmentEndUtc,
            Status = (string)(object)a.Status, UpdatedAtUtc = a.UpdatedAtUtc,
            PaymentMethod = p == null ? null : (string)(object)p.Method, PaymentStatus = p == null ? null : (string)(object)p.Status
        };

    private static void Present(DoctorAppointmentDto row, DateTime now)
    {
        row.AppointmentStartUtc = DateTime.SpecifyKind(row.AppointmentStartUtc, DateTimeKind.Utc);
        row.AppointmentEndUtc = DateTime.SpecifyKind(row.AppointmentEndUtc, DateTimeKind.Utc);
        if (row.UpdatedAtUtc is { } updated) row.UpdatedAtUtc = DateTime.SpecifyKind(updated, DateTimeKind.Utc);
        row.Status = Normalize<AppointmentStatus>(row.Status)!;
        row.PaymentMethod = Normalize<AppointmentPaymentMethod>(row.PaymentMethod);
        row.PaymentStatus = Normalize<AppointmentPaymentStatus>(row.PaymentStatus);
        var valid = ValidTime(row.AppointmentStartUtc, row.AppointmentEndUtc);
        var date = valid ? row.AppointmentStartUtc.AddHours(5.5).Date : DateTime.MinValue.Date;
        var today = now.AddHours(5.5).Date;
        row.IsToday = valid && date == today;
        row.IsUpcoming = valid && date > today && row.Status is "Booked" or "Confirmed";
        row.IsCompleted = row.Status == "Completed";
        row.IsHistory = row.Status is "NoShow" or "Cancelled" || !row.IsCompleted && (!valid || date < today || row.AppointmentEndUtc <= now || row.Status == "Unavailable");
        row.AllowedStatuses = AllowedStatuses(row.Status, row.AppointmentStartUtc, row.AppointmentEndUtc, now);
        row.ContactsUnavailable = true;
    }

    private static bool ValidTime(DateTime start, DateTime end) => start != default && end > start && end < DateTime.MaxValue.AddHours(-6);
    private static string? Normalize<T>(string? value) where T : struct, Enum => value is null ? null : Enum.TryParse<T>(value, out var parsed) && Enum.IsDefined(parsed) ? parsed.ToString() : "Unavailable";

    internal static IReadOnlyList<string> AllowedStatuses(string status, DateTime start, DateTime end, DateTime now)
    {
        if (!ValidTime(start, end) || status is not ("Booked" or "Confirmed")) return [];
        var allowed = new List<string>();
        if (status == "Booked") allowed.Add("Confirmed");
        if (now >= start) allowed.Add("Completed");
        if (now >= end) allowed.Add("NoShow");
        return allowed;
    }

    public async Task<AppointmentStatusResultDto?> UpdateStatusAsync(Guid doctorId, int id, UpdateAppointmentStatusDto request, CancellationToken ct = default)
    {
        await using var mutation = mutations is null ? null : await mutations.BeginAsync(id, ct);
        // Read the scalar status first: an unfamiliar stored enum must not crash a mutation.
        var current = await Query(doctorId).SingleOrDefaultAsync(x => x.Id == id, ct);
        if (current is null) return null;
        if (current.Status != request.ExpectedStatus || current.UpdatedAtUtc != request.ExpectedUpdatedAtUtc)
            throw new DbUpdateConcurrencyException();
        var now = clock.GetUtcNow().UtcDateTime;
        if (!AllowedStatuses(current.Status, current.AppointmentStartUtc, current.AppointmentEndUtc, now).Contains(request.Status))
            throw new InvalidAppointmentStatusTransitionException();
        var appointment = await db.Appointments.SingleAsync(x => x.Id == id && x.DoctorId == doctorId, ct);
        if (appointment.Status.ToString() != current.Status || appointment.UpdatedAtUtc != current.UpdatedAtUtc) throw new DbUpdateConcurrencyException();
        // MySQL datetime(6) persists microseconds. Return exactly the persisted precision.
        var timestamp = new DateTime(now.Ticks - now.Ticks % 10, DateTimeKind.Utc);
        if (appointment.UpdatedAtUtc is { } previous && timestamp <= previous) timestamp = DateTime.SpecifyKind(previous.AddTicks(10), DateTimeKind.Utc);
        db.AppointmentStatusChanges.Add(new() { AppointmentId = id, DoctorId = doctorId, PreviousStatus = current.Status, NewStatus = request.Status, ChangedAtUtc = timestamp });
        appointment.Status = Enum.Parse<AppointmentStatus>(request.Status); appointment.UpdatedAtUtc = timestamp;
        await db.SaveChangesAsync(ct);
        if (mutation is not null) await mutation.CommitAsync(ct);
        return new(id, request.Status, timestamp);
    }
}
