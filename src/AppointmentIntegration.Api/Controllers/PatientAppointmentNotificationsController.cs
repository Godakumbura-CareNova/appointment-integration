using System.Security.Claims;
using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Models;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace AppointmentIntegration.Api.Controllers;

[ApiController]
[Route("api/patient/appointment-notifications")]
[Authorize(Roles = "Patient,User")]
public sealed class PatientAppointmentNotificationsController(AppDbContext db, TimeProvider clock) : ControllerBase
{
    private IQueryable<AppointmentReceipt> Owned(Guid patientId) => db.AppointmentReceipts
        .Where(r => r.PatientId == patientId && r.Status == AppointmentReceiptStatus.Rejected
            && db.Appointments.Any(a => a.Id == r.AppointmentId && a.PatientId == patientId)
            && db.AppointmentPayments.Any(p => p.Id == r.AppointmentPaymentId && p.AppointmentId == r.AppointmentId && p.PatientId == patientId));

    [HttpGet]
    public async Task<IActionResult> List(CancellationToken ct)
    {
        if (!Identity(out var id)) return Unauthorized();
        // Retain every unread notification; bound only the already-read history.
        var owned = Owned(id).AsNoTracking();
        var recentReadIds = owned.Where(r => r.PatientNotificationReadAtUtc != null)
            .OrderByDescending(r => r.ReviewedAtUtc).ThenByDescending(r => r.Id).Take(50).Select(r => r.Id);
        var rows = await owned.Where(r => r.PatientNotificationReadAtUtc == null || recentReadIds.Contains(r.Id))
            .OrderByDescending(r => r.ReviewedAtUtc).ThenByDescending(r => r.Id)
            .Select(r => new { r.Id, r.AppointmentId, Reference = r.AppointmentPayment!.Appointment!.AppointmentReference,
                r.RejectionReason, r.ReviewedAtUtc, r.UploadedAtUtc, r.PatientNotificationReadAtUtc,
                NeedsNewReceipt = r.AppointmentPayment.Method == AppointmentPaymentMethod.BankTransfer
                    && r.AppointmentPayment.Status == AppointmentPaymentStatus.AwaitingBankTransferReceipt
                    && !db.AppointmentReceipts.Any(newer => newer.AppointmentPaymentId == r.AppointmentPaymentId && newer.PatientId == id
                        && (newer.UploadedAtUtc > r.UploadedAtUtc || (newer.UploadedAtUtc == r.UploadedAtUtc && newer.Id > r.Id))) }).ToArrayAsync(ct);
        return Ok(rows.Select(r => new { r.Id, RelatedEntityType = "Appointment", RelatedEntityId = r.AppointmentId,
            Title = "Your appointment receipt was rejected",
            Message = $"Receipt for {r.Reference} was rejected. {r.RejectionReason} " + (r.NeedsNewReceipt ? "Please upload a corrected receipt." : "Open payment details to view the latest status."),
            CreatedAtUtc = DateTime.SpecifyKind(r.ReviewedAtUtc ?? r.UploadedAtUtc, DateTimeKind.Utc), IsRead = r.PatientNotificationReadAtUtc != null }));
    }

    [HttpPost("{notificationId:int:min(1)}/read")]
    public async Task<IActionResult> MarkRead(int notificationId, CancellationToken ct)
    {
        if (!Identity(out var id)) return Unauthorized();
        var receipt = await Owned(id).SingleOrDefaultAsync(r => r.Id == notificationId, ct);
        if (receipt is null) return NotFound();
        receipt.PatientNotificationReadAtUtc ??= clock.GetUtcNow().UtcDateTime;
        await db.SaveChangesAsync(ct);
        return NoContent();
    }

    [HttpPost("read-all")]
    public async Task<IActionResult> MarkAllRead(CancellationToken ct)
    {
        if (!Identity(out var id)) return Unauthorized();
        var unread = Owned(id).Where(r => r.PatientNotificationReadAtUtc == null);
        var now = clock.GetUtcNow().UtcDateTime;
        if (db.Database.IsRelational()) await unread.ExecuteUpdateAsync(set => set.SetProperty(r => r.PatientNotificationReadAtUtc, now), ct);
        else { foreach (var r in await unread.ToArrayAsync(ct)) r.PatientNotificationReadAtUtc = now; await db.SaveChangesAsync(ct); }
        return NoContent();
    }

    private bool Identity(out Guid id) => Guid.TryParse(User.FindFirstValue(ClaimTypes.NameIdentifier), out id) && id != Guid.Empty;
}
