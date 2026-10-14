using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Models;
using AppointmentIntegration.Api.Security;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace AppointmentIntegration.Api.Controllers;

// Read-only staff history. Existing patient payment and receipt mutation endpoints remain authoritative.
[ApiController]
[Route("api/staff/appointment-payments/transactions")]
[Authorize(Policy = AuthorizationPolicies.PharmacyStaff)]
public sealed class StaffAppointmentTransactionsController(AppDbContext db) : ControllerBase
{
    private static readonly string[] Categories = ["All", "Pending", "Successful", "Failed", "Rejected"];

    [HttpGet]
    public async Task<IActionResult> List([FromQuery] string status = "All", [FromQuery] string? method = null,
        [FromQuery] string? search = null, [FromQuery] int page = 1, [FromQuery] int pageSize = 20,
        CancellationToken ct = default)
    {
        AppointmentPaymentMethod? selectedMethod = null;
        if (!string.IsNullOrEmpty(method))
        {
            // Accept public enum names only, not arbitrary numeric enum values.
            if (!Enum.GetNames<AppointmentPaymentMethod>().Contains(method))
                return BadRequest(new { message = "Choose a valid payment method." });
            selectedMethod = Enum.Parse<AppointmentPaymentMethod>(method);
        }
        if (!Categories.Contains(status) || search?.Length > 100 || page < 1 || page > 1000000 || pageSize < 1 || pageSize > 100)
            return BadRequest(new { message = "Check the status, search and page values." });

        var query = Rows();
        if (selectedMethod.HasValue) query = query.Where(r => r.Payment.Method == selectedMethod.Value);
        if (!string.IsNullOrWhiteSpace(search))
        {
            var term = search.Trim();
            query = query.Where(r => r.Appointment.AppointmentReference.Contains(term) || r.Appointment.DoctorName.Contains(term));
        }

        // Counts follow search/method, but remain available for all category buttons.
        var grouped = await query.GroupBy(r => r.Category).Select(g => new { Category = g.Key, Count = g.Count() }).ToArrayAsync(ct);
        int Count(string category) => grouped.FirstOrDefault(g => g.Category == category)?.Count ?? 0;
        var counts = new { all = grouped.Sum(g => g.Count), pending = Count("Pending"), successful = Count("Successful"), failed = Count("Failed"), rejected = Count("Rejected") };
        if (status != "All") query = query.Where(r => r.Category == status);
        var totalCount = await query.CountAsync(ct);
        var totalPages = (int)Math.Ceiling(totalCount / (double)pageSize);
        page = Math.Min(page, Math.Max(1, totalPages));
        var rows = await query.OrderByDescending(r => r.Payment.UpdatedAtUtc).ThenByDescending(r => r.Payment.Id)
            .Skip((page - 1) * pageSize).Take(pageSize).ToArrayAsync(ct);
        return Ok(new { transactions = rows.Select(ToDto), counts, totalCount, page, pageSize, totalPages });
    }

    [HttpGet("{paymentId:int:min(1)}")]
    public async Task<IActionResult> Details(int paymentId, CancellationToken ct)
    {
        var row = await Rows().SingleOrDefaultAsync(r => r.Payment.Id == paymentId, ct);
        if (row is null) return NotFound(new { message = "Appointment payment was not found." });
        var receipts = await db.AppointmentReceipts.AsNoTracking()
            .Where(r => r.AppointmentPaymentId == paymentId && r.AppointmentId == row.Appointment.Id && r.PatientId == row.Payment.PatientId)
            .OrderByDescending(r => r.UploadedAtUtc).ThenByDescending(r => r.Id).ToArrayAsync(ct);
        var attempts = await db.AppointmentOnlinePaymentAttempts.AsNoTracking()
            .Where(a => a.AppointmentPaymentId == paymentId && a.AppointmentId == row.Appointment.Id && a.PatientId == row.Payment.PatientId)
            .OrderByDescending(a => a.AttemptNumber).ThenByDescending(a => a.Id).ToArrayAsync(ct);
        var reconciliations = await db.AppointmentPaymentReconciliations.AsNoTracking()
            .Where(r => r.PaymentId == paymentId && r.AppointmentId == row.Appointment.Id)
            .OrderByDescending(r => r.CreatedAtUtc).ThenByDescending(r => r.Id).ToArrayAsync(ct);
        return Ok(new {
            transaction = ToDto(row),
            receipts = receipts.Select(r => new { r.Id, FileName = r.OriginalFileName, r.ContentType, r.SizeBytes,
                Status = r.Status.ToString(), UploadedAtUtc = Utc(r.UploadedAtUtc), ReviewedAtUtc = Utc(r.ReviewedAtUtc), r.RejectionReason }),
            onlineAttempts = attempts.Select(a => new { a.Id, a.AttemptNumber, a.Amount, a.Currency, Status = a.Status.ToString(),
                CreatedAtUtc = Utc(a.CreatedAtUtc), CompletedAtUtc = Utc(a.CompletedAtUtc), a.FailureMessage }),
            reconciliations = reconciliations.Select(r => new { r.Id, r.Status, r.Reason, CreatedAtUtc = Utc(r.CreatedAtUtc) })
        });
    }

    private IQueryable<PaymentRow> Rows() =>
        from p in db.AppointmentPayments.AsNoTracking()
        join a in db.Appointments.AsNoTracking() on new { p.AppointmentId, p.PatientId } equals new { AppointmentId = a.Id, a.PatientId }
        let rejected = p.Method == AppointmentPaymentMethod.BankTransfer && p.Status == AppointmentPaymentStatus.AwaitingBankTransferReceipt
            && db.AppointmentReceipts.Where(r => r.AppointmentPaymentId == p.Id && r.AppointmentId == a.Id && r.PatientId == p.PatientId)
                .OrderByDescending(r => r.UploadedAtUtc).ThenByDescending(r => r.Id)
                .Select(r => (AppointmentReceiptStatus?)r.Status).FirstOrDefault() == AppointmentReceiptStatus.Rejected
        select new PaymentRow { Payment = p, Appointment = a, Category = rejected ? "Rejected"
            : p.Status == AppointmentPaymentStatus.Successful ? "Successful"
            : p.Status == AppointmentPaymentStatus.Failed ? "Failed" : "Pending" };

    private static object ToDto(PaymentRow r) => new {
        r.Payment.Id, r.Payment.AppointmentId, Reference = r.Appointment.AppointmentReference, r.Payment.PatientId,
        r.Appointment.DoctorName, StartUtc = Utc(r.Appointment.AppointmentStartUtc), AppointmentStatus = r.Appointment.Status.ToString(),
        Method = r.Payment.Method.ToString(), Status = r.Payment.Status.ToString(), r.Category, r.Payment.Amount,
        CreatedAtUtc = Utc(r.Payment.CreatedAtUtc), UpdatedAtUtc = Utc(r.Payment.UpdatedAtUtc), ConfirmedAtUtc = Utc(r.Payment.ConfirmedAtUtc)
    };

    private static DateTime Utc(DateTime value) => DateTime.SpecifyKind(value, DateTimeKind.Utc);
    private static DateTime? Utc(DateTime? value) => value.HasValue ? Utc(value.Value) : null;
    private sealed class PaymentRow
    {
        public AppointmentPayment Payment { get; init; } = null!;
        public Appointment Appointment { get; init; } = null!;
        public string Category { get; init; } = "Pending";
    }
}
