using AppointmentIntegration.Api.Models;
using Microsoft.EntityFrameworkCore;
namespace AppointmentIntegration.Api.Data;
public sealed class AppDbContext(DbContextOptions<AppDbContext> options) : DbContext(options)
{
    public DbSet<PharmacyInformation> PharmacyInformation => Set<PharmacyInformation>();
    public DbSet<ContactInquiry> ContactInquiries => Set<ContactInquiry>();
    protected override void OnModelCreating(ModelBuilder model)
    {
        var information = model.Entity<PharmacyInformation>();
        information.ToTable("PublicPharmacyInformation");
        information.HasKey(x => x.Id);
        information.Property(x => x.Id).ValueGeneratedNever();
        information.Property(x => x.ContentJson).HasColumnType("longtext").IsRequired();
        information.Property(x => x.Revision).IsConcurrencyToken();
        var inquiry = model.Entity<ContactInquiry>();
        inquiry.ToTable("PublicContactInquiries");
        inquiry.HasKey(x => x.Id);
        inquiry.Property(x => x.Name).HasMaxLength(120).IsRequired();
        inquiry.Property(x => x.Email).HasMaxLength(254).IsRequired();
        inquiry.Property(x => x.Phone).HasMaxLength(40).IsRequired();
        inquiry.Property(x => x.Subject).HasMaxLength(200).IsRequired();
        inquiry.Property(x => x.Message).HasMaxLength(5000).IsRequired();
        // MySQL datetime columns do not retain DateTime.Kind; restore UTC for JSON consumers.
        inquiry.Property(x => x.SubmittedAtUtc).HasConversion(
            value => value, value => DateTime.SpecifyKind(value, DateTimeKind.Utc));
        inquiry.Property(x => x.ReviewedAtUtc).HasConversion(
            value => value, value => value.HasValue ? DateTime.SpecifyKind(value.Value, DateTimeKind.Utc) : (DateTime?)null);
        inquiry.HasIndex(x => new { x.SubmittedAtUtc, x.Id });
    }
}
