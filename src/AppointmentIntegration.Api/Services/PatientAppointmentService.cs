using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.DTOs.Appointment;
using AppointmentIntegration.Api.Models;
using AppointmentIntegration.Api.Services.Interfaces;
using Microsoft.EntityFrameworkCore;

namespace AppointmentIntegration.Api.Services;

public sealed class PatientAppointmentService(AppDbContext db, TimeProvider clock) : IPatientAppointmentService
{
    public async Task<IReadOnlyList<AppointmentSummaryDto>> GetAppointmentsAsync(Guid patientId, CancellationToken cancellationToken = default)
    {
        ValidatePatient(patientId);
        var rows = await Query(patientId).ToListAsync(cancellationToken);
        await AddReceiptFeedbackAsync(patientId, rows, cancellationToken);
        var now = clock.GetUtcNow().UtcDateTime;
        return rows.Select(row => Summarize(row, now)).ToList();
    }

    public async Task<AppointmentSummaryDto?> GetAppointmentAsync(Guid patientId, int appointmentId, CancellationToken cancellationToken = default)
    {
        ValidatePatient(patientId);
        var row = await Query(patientId).SingleOrDefaultAsync(row => row.Id == appointmentId, cancellationToken);
        if (row is not null) await AddReceiptFeedbackAsync(patientId, [row], cancellationToken);
        return row is null ? null : Summarize(row, clock.GetUtcNow().UtcDateTime);
    }

    private IQueryable<PatientAppointmentRow> Query(Guid patientId) =>
        from appointment in db.Appointments.AsNoTracking()
        where appointment.PatientId == patientId
        join payment in db.AppointmentPayments.AsNoTracking().Where(payment => payment.PatientId == patientId)
            on appointment.Id equals payment.AppointmentId into payments
        from payment in payments.DefaultIfEmpty()
        // Project enum-backed columns as SQL strings before materialization so unfamiliar
        // stored values can be displayed without failing the entire appointment history.
        select new PatientAppointmentRow
        {
            Id = appointment.Id, AppointmentReference = appointment.AppointmentReference, DoctorName = appointment.DoctorName,
            AppointmentStartUtc = appointment.AppointmentStartUtc, AppointmentEndUtc = appointment.AppointmentEndUtc,
            Status = (string)(object)appointment.Status,
            PaymentMethod = payment == null ? null : (string)(object)payment.Method,
            PaymentStatus = payment == null ? null : (string)(object)payment.Status,
            PaymentId = payment == null ? null : payment.Id
        };

    private sealed class PatientAppointmentRow
    {
        public int? PaymentId { get; init; }
        public AppointmentIntegration.Api.DTOs.AppointmentPayment.AppointmentReceiptFeedbackDto? LatestReceipt { get; set; }
        public int Id { get; init; }
        public string AppointmentReference { get; init; } = string.Empty;
        public string DoctorName { get; init; } = string.Empty;
        public DateTime AppointmentStartUtc { get; init; }
        public DateTime AppointmentEndUtc { get; init; }
        public string Status { get; init; } = string.Empty;
        public string? PaymentMethod { get; init; }
        public string? PaymentStatus { get; init; }
    }

    private static AppointmentSummaryDto Summarize(PatientAppointmentRow appointment, DateTime now)
    {
        var status = Normalize<AppointmentStatus>(appointment.Status)!;
        var validTime = appointment.AppointmentStartUtc != default && appointment.AppointmentEndUtc > appointment.AppointmentStartUtc;
        var section = status is "Completed" or "Cancelled" or "NoShow"
            ? "Previous"
            : status == "Unavailable" || !validTime ? "Unavailable"
            : appointment.AppointmentEndUtc <= now ? "Previous" : "Upcoming";
        var paymentStatus = Normalize<AppointmentPaymentStatus>(appointment.PaymentStatus);
        var paymentMethod = Normalize<AppointmentPaymentMethod>(appointment.PaymentMethod);
        return new()
        {
            Id = appointment.Id,
            AppointmentReference = appointment.AppointmentReference,
            DoctorName = appointment.DoctorName,
            AppointmentStartUtc = DateTime.SpecifyKind(appointment.AppointmentStartUtc, DateTimeKind.Utc),
            AppointmentEndUtc = DateTime.SpecifyKind(appointment.AppointmentEndUtc, DateTimeKind.Utc),
            Status = status,
            Section = section,
            PaymentMethod = paymentMethod,
            PaymentStatus = paymentStatus,
            LatestReceipt = appointment.LatestReceipt,
            CanPay = section == "Upcoming" && paymentMethod != "Unavailable" &&
                paymentStatus is not ("Unavailable" or "Successful" or "ReceiptUnderVerification")
        };
    }

    private static string? Normalize<T>(string? value) where T : struct, Enum => value is null ? null
        : Enum.TryParse<T>(value, out var status) && Enum.IsDefined(status) ? status.ToString() : "Unavailable";

    private async Task AddReceiptFeedbackAsync(Guid patientId, IReadOnlyList<PatientAppointmentRow> rows, CancellationToken ct)
    {
        var ids = rows.Where(r => r.PaymentId.HasValue && r.PaymentMethod == "BankTransfer").Select(r => r.PaymentId!.Value).ToArray();
        if (ids.Length == 0) return;
        // One batched query; select only the newest receipt for each owned payment.
        var latest = await db.AppointmentReceipts.AsNoTracking()
            .Where(r => r.PatientId == patientId && ids.Contains(r.AppointmentPaymentId)
                && !db.AppointmentReceipts.Any(newer => newer.AppointmentPaymentId == r.AppointmentPaymentId && newer.PatientId == patientId
                    && (newer.UploadedAtUtc > r.UploadedAtUtc || (newer.UploadedAtUtc == r.UploadedAtUtc && newer.Id > r.Id))))
            .Select(r => new { r.AppointmentPaymentId, r.AppointmentId, Status = (string)(object)r.Status, r.RejectionReason, r.ReviewedAtUtc }).ToArrayAsync(ct);
        foreach (var row in rows)
        {
            var receipt = latest.FirstOrDefault(r => r.AppointmentPaymentId == row.PaymentId && r.AppointmentId == row.Id);
            if (receipt is not null) row.LatestReceipt = new(Normalize<AppointmentReceiptStatus>(receipt.Status)!, receipt.RejectionReason,
                receipt.ReviewedAtUtc.HasValue ? DateTime.SpecifyKind(receipt.ReviewedAtUtc.Value, DateTimeKind.Utc) : null);
        }
    }

    private static void ValidatePatient(Guid patientId)
    {
        if (patientId == Guid.Empty) throw new ArgumentException("A valid patient identity is required.");
    }
}
