using AppointmentIntegration.Api.Clients;
using AppointmentIntegration.Api.Config;
using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Models;
using AppointmentIntegration.Api.Repositories;
using AppointmentIntegration.Api.Services;
using AppointmentIntegration.Api.Tests.Support;
using Microsoft.AspNetCore.Http;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Moq;
using AppointmentIntegration.Api.Services.Interfaces;
using AppointmentIntegration.Api.DTOs.Cancellation;

namespace AppointmentIntegration.Api.Tests.Integration;

public class AppointmentCancellationConcurrencyTests
{
    private sealed class PausedStorage : IBlobStorageService
    {
        public TaskCompletionSource Started = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource Release = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public bool Deleted;
        public async Task<BlobUploadResult> UploadReceiptAsync(Stream stream, string name, string type, CancellationToken ct = default)
        { Started.SetResult(); await Release.Task.WaitAsync(TimeSpan.FromSeconds(15)); return new() { BlobName = "test-receipt", ContainerName = "test" }; }
        public Task DeleteAsync(string name, CancellationToken ct = default) { Deleted = true; return Task.CompletedTask; }
        public Task<BlobDownloadResult> DownloadReceiptAsync(string name, CancellationToken ct = default) => throw new NotSupportedException();
    }

    [Fact] public async Task Slow_receipt_storage_does_not_lock_cancellation_and_orphan_blob_is_removed()
    {
        var path = Path.Combine(Path.GetTempPath(), "carenova-gcn48-" + Guid.NewGuid().ToString("N") + ".db");
        try
        {
            var options = new DbContextOptionsBuilder<AppDbContext>().UseSqlite($"Data Source={path};Pooling=False;Default Timeout=15").Options;
            await using var writer = new AppDbContext(options); await writer.Database.EnsureCreatedAsync();
            writer.Appointments.Add(new() { Id = 1, PatientId = PaymentFixture.Patient, AppointmentReference = "CN-UPLOAD", DoctorName = "Dr Test", DoctorAvailabilitySlotId = 1, AppointmentStartUtc = DateTime.UtcNow.AddHours(8), AppointmentEndUtc = DateTime.UtcNow.AddHours(9) });
            writer.AppointmentPayments.Add(new() { AppointmentId = 1, PatientId = PaymentFixture.Patient, Method = AppointmentPaymentMethod.BankTransfer, Status = AppointmentPaymentStatus.AwaitingBankTransferReceipt, Amount = 2700, UpdatedAtUtc = DateTime.UtcNow }); await writer.SaveChangesAsync(); writer.ChangeTracker.Clear();
            await using var cancellingDb = new AppDbContext(options); var cancellation = new AppointmentCancellationService(cancellingDb, TimeProvider.System, new AppointmentMutationScope(cancellingDb));
            var eligibility = await cancellation.GetEligibilityAsync(PaymentFixture.Patient, 1);
            var storage = new PausedStorage(); using var http = new HttpClient(new PaymentFixture.DoctorHandler()) { BaseAddress = new("https://example.test/") };
            var payments = new AppointmentPaymentService(new AppointmentPaymentRepository(writer), new DoctorPaymentClient(http, new HttpContextAccessor()), storage, TimeProvider.System, new AppointmentMutationScope(writer));
            var uploading = Task.Run(() => payments.UploadReceiptAsync(PaymentFixture.Patient, 1, PaymentFixture.Receipt())); await storage.Started.Task.WaitAsync(TimeSpan.FromSeconds(15));
            var cancelling = Task.Run(() => cancellation.CancelAsync(PaymentFixture.Patient, 1, new() { ExpectedVersion = eligibility!.Version }));
            var finishedBeforeUpload = await Task.WhenAny(cancelling, Task.Delay(1500)) == cancelling;
            storage.Release.SetResult();
            var uploadError = await Record.ExceptionAsync(async () => await uploading);
            var cancellationError = await Record.ExceptionAsync(async () => await cancelling);
            Assert.True(finishedBeforeUpload, "Blob storage held the appointment database lock."); Assert.Null(cancellationError); Assert.IsType<InvalidOperationException>(uploadError);
            Assert.True(storage.Deleted); Assert.Empty(await cancellingDb.AppointmentReceipts.ToListAsync());
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }
    private sealed class PauseAfterWrite : SaveChangesInterceptor
    {
        public TaskCompletionSource Paused = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource Release = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public override async ValueTask<int> SavedChangesAsync(SaveChangesCompletedEventData data, int result, CancellationToken ct = default)
        {
            Paused.TrySetResult(); await Release.Task.WaitAsync(TimeSpan.FromSeconds(15), ct); return result;
        }
    }
    [Theory]
    [InlineData("method")][InlineData("receipt")][InlineData("verification")][InlineData("checkout")][InlineData("doctor")][InlineData("cancellation")][InlineData("payment-after-cancellation")]
    public async Task Cancellation_serializes_with_actual_competing_service_writes(string competingPath)
    {
        var database = Path.Combine(Path.GetTempPath(), "carenova-gcn48-" + Guid.NewGuid().ToString("N") + ".db");
        try
        {
            DbContextOptions<AppDbContext> Options(PauseAfterWrite? pause = null)
            {
                var options = new DbContextOptionsBuilder<AppDbContext>().UseSqlite($"Data Source={database};Pooling=False;Default Timeout=15");
                if (pause is not null) options.AddInterceptors(pause); return options.Options;
            }
            await using (var seed = new AppDbContext(Options()))
            {
                await seed.Database.EnsureCreatedAsync();
                seed.Appointments.Add(new() { Id = 1, PatientId = PaymentFixture.Patient, DoctorId = Guid.Parse("22222222-2222-2222-2222-222222222222"), AppointmentReference = "CN-RACE", DoctorName = "Dr Test", DoctorAvailabilitySlotId = 10,
                    AppointmentStartUtc = DateTime.UtcNow.AddHours(8), AppointmentEndUtc = DateTime.UtcNow.AddHours(9) });
                if (competingPath is "receipt" or "checkout" or "verification") seed.AppointmentPayments.Add(new() { Id = 1, AppointmentId = 1, PatientId = PaymentFixture.Patient, Amount = 2700,
                    Method = competingPath != "checkout" ? AppointmentPaymentMethod.BankTransfer : AppointmentPaymentMethod.PaymentGateway,
                    Status = competingPath == "verification" ? AppointmentPaymentStatus.ReceiptUnderVerification : competingPath == "receipt" ? AppointmentPaymentStatus.AwaitingBankTransferReceipt : AppointmentPaymentStatus.AwaitingGatewayPayment,
                    UpdatedAtUtc = DateTime.UtcNow });
                if (competingPath == "verification") seed.AppointmentReceipts.Add(new() { AppointmentPaymentId = 1, AppointmentId = 1, PatientId = PaymentFixture.Patient,
                    OriginalFileName = "receipt.pdf", BlobName = "fixture", ContainerName = "test", ContentType = "application/pdf", Status = AppointmentReceiptStatus.PendingVerification, UploadedAtUtc = DateTime.UtcNow });
                await seed.SaveChangesAsync();
            }
            var pause = new PauseAfterWrite();
            await using var writer = new AppDbContext(Options(pause)); await using var cancellingDb = new AppDbContext(Options());
            var cancellation = new AppointmentCancellationService(cancellingDb, TimeProvider.System, new AppointmentMutationScope(cancellingDb));
            var eligibility = await cancellation.GetEligibilityAsync(PaymentFixture.Patient, 1);
            using var fixture = new PaymentFixture(); using var http = new HttpClient(new PaymentFixture.DoctorHandler()) { BaseAddress = new("https://example.test/") };
            var scope = new AppointmentMutationScope(writer); var repository = new AppointmentPaymentRepository(writer);
            var payments = new AppointmentPaymentService(repository, new DoctorPaymentClient(http, new HttpContextAccessor()), new MemoryReceiptStorage(), TimeProvider.System, scope);
            var online = new AppointmentOnlinePaymentService(repository, new PayHerePaymentGateway(Microsoft.Extensions.Options.Options.Create(fixture.Settings), NullLogger<PayHerePaymentGateway>.Instance), Microsoft.Extensions.Options.Options.Create(fixture.Settings), TimeProvider.System, scope);
            async Task Write()
            {
                switch (competingPath)
                {
                    case "method": await payments.SelectPaymentMethodAsync(PaymentFixture.Patient, 1, new() { Method = "Cash" }); break;
                    case "receipt": await payments.UploadReceiptAsync(PaymentFixture.Patient, 1, PaymentFixture.Receipt()); break;
                    case "verification": await payments.VerifyReceiptAsync(PaymentFixture.Staff, 1, new() { Approved = true }); break;
                    case "checkout": await online.StartAsync(PaymentFixture.Patient, 1, PaymentFixture.Billing(), "http://localhost:3000"); break;
                    case "doctor": await new DoctorAppointmentService(writer, TimeProvider.System, Mock.Of<IUserAuthClient>(), new HttpContextAccessor(), NullLogger<DoctorAppointmentService>.Instance, scope)
                        .UpdateStatusAsync(Guid.Parse("22222222-2222-2222-2222-222222222222"), 1, new() { Status = "Confirmed", ExpectedStatus = "Booked" }); break;
                    case "cancellation": case "payment-after-cancellation": await new AppointmentCancellationService(writer, TimeProvider.System, scope).CancelAsync(PaymentFixture.Patient, 1, new() { ExpectedVersion = eligibility!.Version }); break;
                }
            }
            var writing = Task.Run(Write); await pause.Paused.Task.WaitAsync(TimeSpan.FromSeconds(15));
            var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            var waiting = Task.Run<object>(async () => {
                started.SetResult();
                if (competingPath == "payment-after-cancellation") return await new AppointmentPaymentService(new AppointmentPaymentRepository(cancellingDb), new DoctorPaymentClient(http, new HttpContextAccessor()), new MemoryReceiptStorage(), TimeProvider.System, new AppointmentMutationScope(cancellingDb))
                    .SelectPaymentMethodAsync(PaymentFixture.Patient, 1, new() { Method = "Cash" });
                return await cancellation.CancelAsync(PaymentFixture.Patient, 1, new() { ExpectedVersion = eligibility!.Version });
            });
            await started.Task;
            try { Assert.NotSame(waiting, await Task.WhenAny(waiting, Task.Delay(150))); }
            finally { pause.Release.TrySetResult(); }
            await writing;
            if (competingPath == "cancellation")
            {
                Assert.Equal("Cancelled", Assert.IsType<CancellationResponseDto>(await waiting).Status); Assert.Equal(1, await cancellingDb.AppointmentCancellations.CountAsync());
            }
            else
            {
                var failure = await Record.ExceptionAsync(async () => await waiting);
                Assert.True(failure is ArgumentException or DbUpdateConcurrencyException or InvalidOperationException, failure?.ToString() ?? "Conflicting operation unexpectedly succeeded.");
                Assert.Equal(competingPath == "payment-after-cancellation" ? 1 : 0, await cancellingDb.AppointmentCancellations.CountAsync());
            }
        }
        finally { if (File.Exists(database)) File.Delete(database); }
    }
}
