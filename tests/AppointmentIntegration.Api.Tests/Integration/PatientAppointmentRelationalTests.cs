using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Models;
using AppointmentIntegration.Api.Services;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;

namespace AppointmentIntegration.Api.Tests.Integration;

public class PatientAppointmentRelationalTests
{
    [Theory]
    [InlineData("Status", "Rescheduled")]
    [InlineData("PaymentStatus", "Refunded")]
    [InlineData("PaymentMethod", "FutureMethod")]
    public async Task UnfamiliarStoredStringsDoNotPreventReadingOtherAppointmentInformation(string field, string value)
    {
        await using var connection = new SqliteConnection("Data Source=:memory:"); await connection.OpenAsync();
        await using var db = new AppDbContext(new DbContextOptionsBuilder<AppDbContext>().UseSqlite(connection).Options);
        await db.Database.EnsureCreatedAsync(); var patient = Guid.NewGuid();
        db.Appointments.Add(new() { Id = 1, PatientId = patient, DoctorId = Guid.NewGuid(), DoctorName = "Dr Test", AppointmentReference = "CN-APT-RELATIONAL", DoctorAvailabilitySlotId = 1,
            AppointmentStartUtc = DateTime.UtcNow.AddDays(1), AppointmentEndUtc = DateTime.UtcNow.AddDays(1).AddMinutes(30) });
        db.AppointmentPayments.Add(new() { Id = 1, AppointmentId = 1, PatientId = patient, Method = AppointmentPaymentMethod.Cash, Status = AppointmentPaymentStatus.Pending, Amount = 2700 });
        await db.SaveChangesAsync();
        if (field == "Status") await db.Database.ExecuteSqlInterpolatedAsync($"UPDATE Appointments SET Status = {value} WHERE Id = 1");
        else if (field == "PaymentStatus") await db.Database.ExecuteSqlInterpolatedAsync($"UPDATE AppointmentPayments SET Status = {value} WHERE Id = 1");
        else await db.Database.ExecuteSqlInterpolatedAsync($"UPDATE AppointmentPayments SET Method = {value} WHERE Id = 1");
        db.ChangeTracker.Clear();
        var service = new PatientAppointmentService(db, TimeProvider.System);
        var result = Assert.Single(await service.GetAppointmentsAsync(patient));
        Assert.Equal("Dr Test", result.DoctorName); Assert.Equal("CN-APT-RELATIONAL", result.AppointmentReference); Assert.False(result.CanPay);
        Assert.Equal("Unavailable", field == "Status" ? result.Status : field == "PaymentStatus" ? result.PaymentStatus : result.PaymentMethod);
        Assert.NotNull(await service.GetAppointmentAsync(patient, 1));
        Assert.Empty(await service.GetAppointmentsAsync(Guid.NewGuid()));
    }
}
