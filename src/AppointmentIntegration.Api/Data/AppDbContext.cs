using AppointmentIntegration.Api.Models;
using Microsoft.EntityFrameworkCore;

namespace AppointmentIntegration.Api.Data;

public class AppDbContext : DbContext
{
    public AppDbContext(DbContextOptions<AppDbContext> options)
        : base(options)
    {
    }

    public DbSet<Appointment> Appointments => Set<Appointment>();
    public DbSet<AppointmentStatusChange> AppointmentStatusChanges => Set<AppointmentStatusChange>();

    public DbSet<AppointmentPayment> AppointmentPayments =>
        Set<AppointmentPayment>();

    public DbSet<AppointmentReceipt> AppointmentReceipts =>
        Set<AppointmentReceipt>();

    public DbSet<AppointmentOnlinePaymentAttempt> AppointmentOnlinePaymentAttempts =>
    Set<AppointmentOnlinePaymentAttempt>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        var appointment = modelBuilder.Entity<Appointment>();

        appointment.HasKey(x => x.Id);

        appointment.Property(x => x.AppointmentReference)
            .IsRequired()
            .HasMaxLength(50);

        appointment.HasIndex(x => x.AppointmentReference)
            .IsUnique();

        appointment.Property(x => x.DoctorName)
            .IsRequired()
            .HasMaxLength(150);

        /*
         * Critical GCN-44 rule:
         *
         * A Doctor Payment availability slot may only belong
         * to one appointment.
         *
         * This protects against two requests booking the same
         * slot at nearly the same time.
         */
        appointment.HasIndex(x => x.DoctorAvailabilitySlotId)
            .IsUnique();

        appointment.Property(x => x.Status)
            .HasConversion<string>()
            .IsConcurrencyToken()
            .HasMaxLength(30)
            .IsRequired();

        appointment.Property(x => x.UpdatedAtUtc).IsConcurrencyToken();
        var change = modelBuilder.Entity<AppointmentStatusChange>();
        change.HasKey(x => x.Id);
        change.Property(x => x.PreviousStatus).IsRequired().HasMaxLength(30);
        change.Property(x => x.NewStatus).IsRequired().HasMaxLength(30);
        change.HasIndex(x => new { x.AppointmentId, x.ChangedAtUtc });
        change.HasOne<Appointment>().WithMany().HasForeignKey(x => x.AppointmentId).OnDelete(DeleteBehavior.Restrict);


        var payment = modelBuilder.Entity<AppointmentPayment>();

        payment.HasKey(x => x.Id);

        /*
         * One payment record per appointment.
         */
        payment.HasIndex(x => x.AppointmentId)
            .IsUnique();

        payment.Property(x => x.Amount)
            .HasPrecision(12, 2);

        payment.Property(x => x.Method)
            .HasConversion<string>()
            .HasMaxLength(30)
            .IsRequired();

        payment.Property(x => x.Status)
            .HasConversion<string>()
            .HasMaxLength(40)
            .IsRequired();

        payment.HasOne(x => x.Appointment)
            .WithOne()
            .HasForeignKey<AppointmentPayment>(
                x => x.AppointmentId)
            .OnDelete(DeleteBehavior.Cascade);


        var receipt = modelBuilder.Entity<AppointmentReceipt>();

        receipt.HasKey(x => x.Id);

        receipt.Property(x => x.OriginalFileName)
            .IsRequired()
            .HasMaxLength(255);

        receipt.Property(x => x.BlobName)
            .IsRequired()
            .HasMaxLength(500);

        receipt.Property(x => x.ContainerName)
            .IsRequired()
            .HasMaxLength(100);

        receipt.Property(x => x.ContentType)
            .IsRequired()
            .HasMaxLength(100);

        receipt.Property(x => x.Status)
            .HasConversion<string>()
            .HasMaxLength(40)
            .IsRequired();

        receipt.HasOne(x => x.AppointmentPayment)
            .WithMany()
            .HasForeignKey(x => x.AppointmentPaymentId)
            .OnDelete(DeleteBehavior.Cascade);

            var onlineAttempt =
    modelBuilder.Entity<AppointmentOnlinePaymentAttempt>();

onlineAttempt.HasKey(x => x.Id);

onlineAttempt.HasIndex(x => x.GatewayReference)
    .IsUnique();

onlineAttempt.Property(x => x.GatewayReference)
    .IsRequired()
    .HasMaxLength(100);

onlineAttempt.Property(x => x.Amount)
    .HasPrecision(12, 2);

onlineAttempt.Property(x => x.Currency)
    .IsRequired()
    .HasMaxLength(3);

onlineAttempt.Property(x => x.Status)
    .HasConversion<string>()
    .HasMaxLength(30)
    .IsRequired();

onlineAttempt.HasOne(x => x.AppointmentPayment)
    .WithMany()
    .HasForeignKey(x => x.AppointmentPaymentId)
    .OnDelete(DeleteBehavior.Cascade);
    }
}
