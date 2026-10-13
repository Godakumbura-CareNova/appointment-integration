using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.DTOs.Cancellation;
using AppointmentIntegration.Api.Models;
using AppointmentIntegration.Api.Services.Interfaces;
using Microsoft.EntityFrameworkCore;

namespace AppointmentIntegration.Api.Services;

public sealed class AppointmentCancellationService(AppDbContext db, TimeProvider clock, IAppointmentMutationScope mutations) : IAppointmentCancellationService
{
    public async Task<CancellationEligibilityDto?> GetEligibilityAsync(Guid patientId, int appointmentId, CancellationToken ct = default)
    {
        var snapshot = await Snapshot(patientId, appointmentId, ct);
        if (snapshot is null) return null;
        var decision = AppointmentCancellationPolicy.Evaluate(snapshot, clock.GetUtcNow().UtcDateTime);
        var existing = await Existing(patientId, appointmentId, ct);
        return new(appointmentId, decision.Allowed, decision.ReasonCode, decision.Message, decision.RefundOutcome, decision.RefundAmount,
            decision.RequiresNoRefundAcknowledgement, Version(snapshot, decision), existing);
    }

    public async Task<CancellationResponseDto> CancelAsync(Guid patientId, int appointmentId, CancelAppointmentRequestDto request, CancellationToken ct = default)
    {
        if (patientId == Guid.Empty) throw new ArgumentException("A valid patient identity is required.");
        if (request.ExpectedVersion.Length != 64 || request.Reason?.Length > 500) throw new ArgumentException("Refresh the cancellation information and check your reason.");
        await using var mutation = await mutations.BeginAsync(appointmentId, ct);
        var snapshot = await Snapshot(patientId, appointmentId, ct) ?? throw new KeyNotFoundException("Appointment not found.");
        var existing = await Existing(patientId, appointmentId, ct);
        if (existing is not null) return existing;
        var now = clock.GetUtcNow().UtcDateTime;
        var decision = AppointmentCancellationPolicy.Evaluate(snapshot, now);
        if (!decision.Allowed) throw new ArgumentException(decision.Message);
        if (request.ExpectedVersion != Version(snapshot, decision)) throw new DbUpdateConcurrencyException("Cancellation information changed. Refresh and confirm again.");
        if (decision.RequiresNoRefundAcknowledgement && !request.AcknowledgeNoRefund) throw new ArgumentException("Confirm that you understand no refund is available.");
        var appointment = await db.Appointments.SingleAsync(x => x.Id == appointmentId && x.PatientId == patientId, ct);
        now = new DateTime(now.Ticks - now.Ticks % 10, DateTimeKind.Utc);
        var cancellation = new AppointmentCancellation { AppointmentId = appointmentId, PatientId = patientId, CancelledAtUtc = now, PreviousStatus = snapshot.Status,
            Reason = string.IsNullOrWhiteSpace(request.Reason) ? null : request.Reason.Trim(), PaymentId = snapshot.PaymentId, PaymentMethod = snapshot.PaymentMethod,
            PaymentStatus = snapshot.PaymentStatus, PaymentAmount = snapshot.Amount, RefundOutcome = decision.RefundOutcome, RefundAmount = decision.RefundAmount, DecisionMessage = decision.Message };
        db.AppointmentCancellations.Add(cancellation);
        if (decision.RefundOutcome == "Eligible") db.RefundRecords.Add(new() { Cancellation = cancellation, Amount = decision.RefundAmount, CreatedAtUtc = now });
        appointment.Status = AppointmentStatus.Cancelled; appointment.UpdatedAtUtc = now;
        await db.SaveChangesAsync(ct); await mutation.CommitAsync(ct);
        return Result(cancellation, appointment.AppointmentReference);
    }

    private async Task<CancellationSnapshot?> Snapshot(Guid patientId, int id, CancellationToken ct)
    {
        if (patientId == Guid.Empty) throw new ArgumentException("A valid patient identity is required.");
        var row = await (from a in db.Appointments.AsNoTracking() where a.Id == id && a.PatientId == patientId
            join p in db.AppointmentPayments.AsNoTracking() on a.Id equals p.AppointmentId into payments from p in payments.DefaultIfEmpty()
            select new { a.Id, a.PatientId, Status = (string)(object)a.Status, a.AppointmentStartUtc, a.AppointmentEndUtc, a.UpdatedAtUtc,
                PaymentId = p == null ? (int?)null : p.Id, PaymentOwner = p == null ? (Guid?)null : p.PatientId,
                Method = p == null ? null : (string)(object)p.Method, PaymentStatus = p == null ? null : (string)(object)p.Status,
                Amount = p == null ? 0 : p.Amount, PaymentUpdated = p == null ? (DateTime?)null : p.UpdatedAtUtc }).SingleOrDefaultAsync(ct);
        if (row is null) return null;
        var attempts = await db.AppointmentOnlinePaymentAttempts.AsNoTracking().Where(x => x.AppointmentId == id).OrderBy(x => x.Id)
            .Select(x => new { x.Id, Status = (string)(object)x.Status, x.CompletedAtUtc }).ToListAsync(ct);
        var inconsistent = row.PaymentOwner.HasValue && row.PaymentOwner != patientId || attempts.Any(x => x.Status is not ("Pending" or "Succeeded" or "Failed" or "Cancelled"));
        return new(row.Id, row.PatientId, row.Status, row.AppointmentStartUtc, row.AppointmentEndUtc, row.UpdatedAtUtc, row.PaymentId,
            inconsistent ? "Unavailable" : row.Method, row.PaymentStatus, row.Amount, row.PaymentUpdated, attempts.Any(x => x.Status == "Pending"), JsonSerializer.Serialize(attempts), attempts.Any(x => x.Status == "Succeeded"));
    }

    private async Task<CancellationResponseDto?> Existing(Guid patientId, int id, CancellationToken ct)
    {
        var cancellation = await db.AppointmentCancellations.AsNoTracking().SingleOrDefaultAsync(x => x.AppointmentId == id && x.PatientId == patientId, ct);
        if (cancellation is null) return null;
        var reference = await db.Appointments.Where(x => x.Id == id && x.PatientId == patientId).Select(x => x.AppointmentReference).SingleAsync(ct);
        return Result(cancellation, reference);
    }
    private static CancellationResponseDto Result(AppointmentCancellation record, string reference) => new(record.AppointmentId, reference, "Cancelled", DateTime.SpecifyKind(record.CancelledAtUtc, DateTimeKind.Utc),
        record.RefundOutcome, record.RefundAmount, record.RefundOutcome == "Eligible" ? "PendingManualProcessing" : null, record.Reason, record.DecisionMessage);
    private static string Version(CancellationSnapshot snapshot, CancellationDecision decision) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new { snapshot, decision }))));
}
