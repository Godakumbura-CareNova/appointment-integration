using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.DTOs.PublicContent;
using AppointmentIntegration.Api.Models;
using Microsoft.EntityFrameworkCore;
namespace AppointmentIntegration.Api.Services;
public sealed class ContactInquiryService(AppDbContext db)
{
    public async Task<ContactInquiry> SubmitAsync(ContactInquiryRequestDto request, CancellationToken token)
    {
        var inquiry = new ContactInquiry {
            Id = Guid.NewGuid(), Name = request.Name.Trim(), Email = request.Email.Trim(), Phone = request.Phone.Trim(),
            Subject = request.Subject.Trim(), Message = request.Message.Trim(), SubmittedAtUtc = DateTime.UtcNow
        };
        db.ContactInquiries.Add(inquiry);
        await db.SaveChangesAsync(token);
        return inquiry;
    }
    public async Task<object> ListAsync(int page, int pageSize, CancellationToken token)
    {
        var total = await db.ContactInquiries.CountAsync(token);
        var items = await db.ContactInquiries.AsNoTracking().OrderByDescending(x => x.SubmittedAtUtc).ThenBy(x => x.Id)
            .Skip((page - 1) * pageSize).Take(pageSize).ToListAsync(token);
        return new { items, page, pageSize, totalCount = total, totalPages = (int)Math.Ceiling(total / (double)pageSize) };
    }
    public async Task<ContactInquiry?> ReviewAsync(Guid id, CancellationToken token)
    {
        var inquiry = await db.ContactInquiries.FindAsync([id], token);
        if (inquiry is null) return null;
        inquiry.ReviewedAtUtc ??= DateTime.UtcNow;
        await db.SaveChangesAsync(token);
        return inquiry;
    }
}
