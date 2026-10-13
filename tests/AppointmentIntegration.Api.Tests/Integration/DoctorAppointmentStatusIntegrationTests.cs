using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Models;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Microsoft.AspNetCore.TestHost;
using AppointmentIntegration.Api.Clients;
using AppointmentIntegration.Api.Services;
using AppointmentIntegration.Api.Tests.Support;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging.Abstractions;

namespace AppointmentIntegration.Api.Tests.Integration;

public class DoctorAppointmentStatusIntegrationTests
{
    [Theory]
    [InlineData("Booked", "Confirmed", -1, 200)]
    [InlineData("Booked", "Completed", -1, 400)]
    [InlineData("Confirmed", "Completed", 0, 200)]
    [InlineData("Booked", "NoShow", 29, 400)]
    [InlineData("Confirmed", "NoShow", 30, 200)]
    [InlineData("Completed", "Confirmed", 60, 400)]
    [InlineData("Cancelled", "NoShow", 60, 400)]
    [InlineData("Booked", "Cancelled", 60, 400)]
    [InlineData("Booked", "garbage", 60, 400)]
    public async Task EnforcesStatusAndExactTimeBoundaries(string from, string to, int elapsedMinutes, int expected)
    {
        var start = new DateTime(2026, 10, 11, 18, 30, 0, DateTimeKind.Utc);
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(true);
        using var timed = factory.WithWebHostBuilder(builder => builder.ConfigureServices(services => services.AddSingleton<TimeProvider>(new FixedClock(start.AddMinutes(elapsedMinutes)))));
        using var client = timed.CreateClient(); client.DefaultRequestHeaders.Add("X-Test-Role", "Doctor"); client.DefaultRequestHeaders.Add("X-Test-Patient", DoctorAppointmentsIntegrationTests.Doctor.ToString());
        using (var scope = timed.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>(); await db.Database.EnsureCreatedAsync();
            db.Appointments.Add(new() { Id = 1, AppointmentReference = "BOUNDARY", DoctorId = DoctorAppointmentsIntegrationTests.Doctor, PatientId = Guid.NewGuid(), DoctorName = "Test", DoctorAvailabilitySlotId = 100, AppointmentStartUtc = start, AppointmentEndUtc = start.AddMinutes(30), Status = Enum.Parse<AppointmentStatus>(from) });
            await db.SaveChangesAsync();
        }
        var result = await client.PatchAsJsonAsync("/api/doctor/appointments/1/status", new { status = to, expectedStatus = from, expectedUpdatedAtUtc = (string?)null });
        Assert.Equal(expected, (int)result.StatusCode);
    }

    [Fact]
    public async Task SriLankaCalendarAndUniquePatientsDriveViewsAndStatistics()
    {
        var now = new DateTime(2026, 10, 11, 18, 29, 59, DateTimeKind.Utc);
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(true);
        using var timed = factory.WithWebHostBuilder(builder => builder.ConfigureServices(services => services.AddSingleton<TimeProvider>(new FixedClock(now))));
        using var client = timed.CreateClient(); client.DefaultRequestHeaders.Add("X-Test-Role", "Doctor"); client.DefaultRequestHeaders.Add("X-Test-Patient", DoctorAppointmentsIntegrationTests.Doctor.ToString());
        using (var scope = timed.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>(); await db.Database.EnsureCreatedAsync(); var patient = Guid.NewGuid();
            foreach (var (id, start) in new[] { (1, now), (2, now.AddSeconds(1)) })
                db.Appointments.Add(new() { Id = id, AppointmentReference = $"DATE-{id}", PatientId = patient, DoctorId = DoctorAppointmentsIntegrationTests.Doctor, DoctorName = "Test", DoctorAvailabilitySlotId = id, AppointmentStartUtc = start, AppointmentEndUtc = start.AddMinutes(30) });
            await db.SaveChangesAsync();
        }
        var list = await client.GetFromJsonAsync<JsonElement>("/api/doctor/appointments");
        var stats = list.GetProperty("statistics"); Assert.Equal(1, stats.GetProperty("today").GetInt32()); Assert.Equal(1, stats.GetProperty("upcoming").GetInt32()); Assert.Equal(1, stats.GetProperty("patientCount").GetInt32());
    }

    internal sealed class FixedClock(DateTime now) : TimeProvider { public override DateTimeOffset GetUtcNow() => new(now); }

    [Fact]
    public async Task OngoingAppointmentFromPreviousCalendarDayRemainsInHistory()
    {
        using var f = new PaymentFixture(true); var row = await f.Db.Appointments.SingleAsync();
        row.AppointmentStartUtc = new DateTime(2026, 10, 11, 18, 15, 0, DateTimeKind.Utc); row.AppointmentEndUtc = row.AppointmentStartUtc.AddMinutes(30); await f.Db.SaveChangesAsync();
        using var http = new HttpClient();
        var service = new DoctorAppointmentService(f.Db, new FixedClock(new DateTime(2026, 10, 11, 18, 30, 0, DateTimeKind.Utc)), new UserAuthClient(http), new HttpContextAccessor(), NullLogger<DoctorAppointmentService>.Instance);
        var appointment = Assert.Single((await service.GetAppointmentsAsync(DoctorAppointmentsIntegrationTests.Doctor)).Appointments);
        Assert.True(appointment.IsHistory); Assert.False(appointment.IsToday); Assert.Contains("Completed", appointment.AllowedStatuses);
    }

    [Fact]
    public async Task ScheduleUsesOneClockSnapshotAcrossMidnight()
    {
        using var f = new PaymentFixture(true); var row = await f.Db.Appointments.SingleAsync();
        row.AppointmentStartUtc = new DateTime(2026, 10, 11, 18, 15, 0, DateTimeKind.Utc); row.AppointmentEndUtc = row.AppointmentStartUtc.AddMinutes(30);
        f.Db.Appointments.Add(new() { Id = 2, AppointmentReference = "SECOND", PatientId = row.PatientId, DoctorId = row.DoctorId, DoctorName = "Test", DoctorAvailabilitySlotId = 101, AppointmentStartUtc = row.AppointmentStartUtc, AppointmentEndUtc = row.AppointmentEndUtc }); await f.Db.SaveChangesAsync();
        using var http = new HttpClient(); var service = new DoctorAppointmentService(f.Db, new AdvancingClock(), new UserAuthClient(http), new HttpContextAccessor(), NullLogger<DoctorAppointmentService>.Instance);
        Assert.Equal(2, (await service.GetAppointmentsAsync(row.DoctorId)).Statistics.Today);
    }

    private sealed class AdvancingClock : TimeProvider
    {
        int reads;
        public override DateTimeOffset GetUtcNow() => new(new DateTime(2026, 10, 11, 18, 29, 59, DateTimeKind.Utc).AddSeconds(reads++));
    }

    [Fact]
    public async Task FailedAuditInsertRollsBackAppointmentStatus()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(true); await factory.Seed();
        using (var scope = factory.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>(); var row = await db.Appointments.SingleAsync();
            row.AppointmentStartUtc = DateTime.UtcNow.AddHours(1); row.AppointmentEndUtc = DateTime.UtcNow.AddHours(2); await db.SaveChangesAsync();
            await db.Database.ExecuteSqlRawAsync("CREATE TRIGGER FailAudit BEFORE INSERT ON AppointmentStatusChanges BEGIN SELECT RAISE(ABORT, 'test audit outage'); END;");
        }
        using var client = factory.Client("Doctor", DoctorAppointmentsIntegrationTests.Doctor);
        Assert.Equal(HttpStatusCode.InternalServerError, (await client.PatchAsJsonAsync("/api/doctor/appointments/1/status", new { status = "Confirmed", expectedStatus = "Booked", expectedUpdatedAtUtc = (string?)null })).StatusCode);
        using var check = factory.Services.CreateScope(); var saved = check.ServiceProvider.GetRequiredService<AppDbContext>();
        Assert.Equal(AppointmentStatus.Booked, (await saved.Appointments.SingleAsync()).Status); Assert.Empty(await saved.AppointmentStatusChanges.ToListAsync());
    }

    [Fact]
    public async Task RacingWriterCannotOverwriteAStatusOrLeaveAnAudit()
    {
        using var fixture = new PaymentFixture(true);
        var race = new RacingWriter();
        await using var db = new AppDbContext(new DbContextOptionsBuilder<AppDbContext>().UseSqlite(fixture.Db.Database.GetDbConnection()).AddInterceptors(race).Options);
        using var http = new HttpClient();
        var service = new DoctorAppointmentService(db, TimeProvider.System, new UserAuthClient(http), new HttpContextAccessor(), NullLogger<DoctorAppointmentService>.Instance);
        await Assert.ThrowsAsync<DbUpdateConcurrencyException>(() => service.UpdateStatusAsync(DoctorAppointmentsIntegrationTests.Doctor, 1, new() { Status = "Confirmed", ExpectedStatus = "Booked" }));
        fixture.Db.ChangeTracker.Clear();
        Assert.Equal(AppointmentStatus.Confirmed, (await fixture.Db.Appointments.SingleAsync()).Status); Assert.Empty(await fixture.Db.AppointmentStatusChanges.ToListAsync());
    }

    [Fact]
    public async Task InvalidDatesAndUnknownStatusesRemainReadableWithoutActions()
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(true); await factory.Seed();
        using (var scope = factory.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>(); var row = await db.Appointments.SingleAsync(); row.AppointmentStartUtc = DateTime.MaxValue; row.AppointmentEndUtc = DateTime.MaxValue; await db.SaveChangesAsync();
            await db.Database.ExecuteSqlRawAsync("UPDATE Appointments SET Status = 'FutureUnknownStatus' WHERE Id = 1");
        }
        using var client = factory.Client("Doctor", DoctorAppointmentsIntegrationTests.Doctor);
        var rowResult = await client.GetFromJsonAsync<JsonElement>("/api/doctor/appointments/1");
        Assert.Equal("Unavailable", rowResult.GetProperty("status").GetString()); Assert.Empty(rowResult.GetProperty("allowedStatuses").EnumerateArray()); Assert.True(rowResult.GetProperty("isHistory").GetBoolean());
    }

    private sealed class RacingWriter : SaveChangesInterceptor
    {
        bool fired;
        public override async ValueTask<InterceptionResult<int>> SavingChangesAsync(DbContextEventData data, InterceptionResult<int> result, CancellationToken ct = default)
        {
            if (!fired && data.Context!.ChangeTracker.Entries<AppointmentStatusChange>().Any())
            {
                fired = true;
                await data.Context.Database.ExecuteSqlRawAsync("UPDATE Appointments SET Status = 'Confirmed', UpdatedAtUtc = '2026-10-11 10:00:00' WHERE Id = 1", ct);
            }
            return result;
        }
    }
}
