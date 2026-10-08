using System.Text.Json;
using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.DTOs.PublicContent;
using AppointmentIntegration.Api.Models;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
namespace AppointmentIntegration.Api.Services;

public sealed class InformationConflictException : Exception;
public sealed class PharmacyInformationService(AppDbContext db, IOptions<PublicContentOptions> defaults, IWebHostEnvironment environment) : Interfaces.IPharmacyInformationReader
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    public async Task<PharmacyInformationDto> GetAsync(CancellationToken token)
    {
        var row = await db.PharmacyInformation.AsNoTracking().SingleOrDefaultAsync(x => x.Id == 1, token);
        if (row is null) return new() { Introduction = defaults.Value.Introduction, Services = defaults.Value.Services };
        var content = JsonSerializer.Deserialize<PharmacyInformationDto>(row.ContentJson, JsonOptions)
            ?? throw new JsonException("Pharmacy information is unavailable.");
        content.Revision = row.Revision;
        return content;
    }
    public async Task<PharmacyInformationDto> SaveAsync(PharmacyInformationDto content, CancellationToken token)
    {
        foreach (var image in content.Images)
        {
            var path = Path.Combine(environment.ContentRootPath, "wwwroot", image.Url.TrimStart('/').Replace('/', Path.DirectorySeparatorChar));
            if (!File.Exists(path)) throw new ArgumentException("One of the photographs is unavailable. Upload it again before saving.");
        }
        var row = await db.PharmacyInformation.SingleOrDefaultAsync(x => x.Id == 1, token);
        if (content.Revision != (row?.Revision ?? Guid.Empty)) throw new InformationConflictException();
        var creating = row is null;
        if (creating) { row = new(); db.PharmacyInformation.Add(row); }
        content.Revision = Guid.NewGuid();
        row!.Revision = content.Revision;
        row.UpdatedAtUtc = DateTime.UtcNow;
        row.ContentJson = JsonSerializer.Serialize(content, JsonOptions);
        try { await db.SaveChangesAsync(token); }
        catch (DbUpdateConcurrencyException) { throw new InformationConflictException(); }
        catch (DbUpdateException) when (creating) {
            db.ChangeTracker.Clear();
            if (await db.PharmacyInformation.AnyAsync(x => x.Id == 1, token)) throw new InformationConflictException();
            throw;
        }
        return content;
    }
}
