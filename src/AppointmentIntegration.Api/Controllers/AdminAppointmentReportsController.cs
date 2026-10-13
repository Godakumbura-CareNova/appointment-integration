using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Models;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace AppointmentIntegration.Api.Controllers;
[ApiController]
[Route("api/admin/reports/appointment-income")]
[Authorize(Roles = "Admin")]
public sealed class AdminAppointmentReportsController(AppDbContext db, TimeProvider clock) : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> Income(DateTimeOffset from, DateTimeOffset to, CancellationToken ct = default)
    {
        // A selectable January 2000 period can start in UTC December 1999 (including Monday-based weeks).
        if (from.Year < 1999 || to <= from || to - from > TimeSpan.FromDays(32))
            return BadRequest(new { message = "Choose a reporting period of at most 32 days." });
        var start = from.UtcDateTime; var end = to.UtcDateTime; var now = clock.GetUtcNow().UtcDateTime;
        var paid = db.AppointmentPayments.AsNoTracking().Where(p => p.Status == AppointmentPaymentStatus.Successful &&
            !db.AppointmentPaymentReconciliations.Any(r => r.PaymentId == p.Id));
        var undatedSuccessfulCount = await paid.CountAsync(p => p.ConfirmedAtUtc == null, ct);
        var rows = await paid.Where(p => p.ConfirmedAtUtc >= start && p.ConfirmedAtUtc < end && p.ConfirmedAtUtc <= now)
            .GroupBy(p => p.ConfirmedAtUtc!.Value.AddMinutes(330).Date)
            .Select(g => new { Date = g.Key, Amount = g.Sum(p => p.Amount), Count = g.Count() }).OrderBy(g => g.Date).ToArrayAsync(ct);
        var days = rows.Select(row => new { Date = row.Date.ToString("yyyy-MM-dd"), row.Amount, row.Count });
        return Ok(new { days, undatedSuccessfulCount, currency = "LKR", timeZone = "Asia/Colombo", generatedAtUtc = now });
    }
}
