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
            .HasMaxLength(30)
            .IsRequired();
    }
}