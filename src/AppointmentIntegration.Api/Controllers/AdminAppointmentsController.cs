using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Models;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace AppointmentIntegration.Api.Controllers;

[ApiController]
[Route("api/admin/appointments")]
[Authorize(Roles = "Admin")]
public sealed class AdminAppointmentsController(AppDbContext db) : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> List([FromQuery] string? search, [FromQuery] int page = 1,
        [FromQuery] int pageSize = 20, CancellationToken ct = default)
    {
        if (page < 1 || page > 1000000 || pageSize < 1 || pageSize > 100 || search?.Length > 100)
            return BadRequest(new { message = "Check the search and page values." });
        var query = db.Appointments.AsNoTracking();
        if (!string.IsNullOrWhiteSpace(search))
        {
            var term = search.Trim();
            query = query.Where(a => a.AppointmentReference.Contains(term) || a.DoctorName.Contains(term));
        }
        var totalCount = await query.CountAsync(ct);
        var ids = await query.OrderByDescending(a => a.CreatedAtUtc).ThenByDescending(a => a.Id)
            .Skip((page - 1) * pageSize).Take(pageSize).Select(a => a.Id).ToArrayAsync(ct);
        var rows = await (from a in query where ids.Contains(a.Id)
            join payment in db.AppointmentPayments.AsNoTracking() on new { AppointmentId = a.Id, a.PatientId }
                equals new { payment.AppointmentId, payment.PatientId } into payments
            from p in payments.DefaultIfEmpty()
            orderby a.CreatedAtUtc descending, a.Id descending
            select new { a.Id, Reference = a.AppointmentReference, a.PatientId, a.DoctorName,
                Start = a.AppointmentStartUtc, Status = (string)(object)a.Status,
                Method = p == null ? null : (string)(object)p.Method,
                PaymentStatus = p == null ? null : (string)(object)p.Status }).ToArrayAsync(ct);
        var items = rows.Select(a => new { a.Id, a.Reference, a.PatientId, a.DoctorName,
            StartUtc = DateTime.SpecifyKind(a.Start, DateTimeKind.Utc), Status = Normalize<AppointmentStatus>(a.Status),
            PaymentMethod = Normalize<AppointmentPaymentMethod>(a.Method), PaymentStatus = Normalize<AppointmentPaymentStatus>(a.PaymentStatus) });
        return Ok(new { items, totalCount, page, pageSize, totalPages = (int)Math.Ceiling((double)totalCount / pageSize) });
    }

    private static string? Normalize<T>(string? value) where T : struct, Enum => value is null ? null
        : Enum.TryParse<T>(value, out var parsed) && Enum.IsDefined(parsed) ? parsed.ToString() : "Unavailable";
}
