using System.Net;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using AppointmentIntegration.Api.Clients;
using AppointmentIntegration.Api.Config;
using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.DTOs.AppointmentPayment;
using AppointmentIntegration.Api.Models;
using AppointmentIntegration.Api.Repositories;
using AppointmentIntegration.Api.Services;
using AppointmentIntegration.Api.Services.Interfaces;
using Microsoft.AspNetCore.Http;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;

namespace AppointmentIntegration.Api.Tests.Support;

internal sealed class PaymentFixture : IDisposable
{
    public static readonly Guid Patient = Guid.Parse("11111111-1111-1111-1111-111111111111");
    public static readonly Guid Staff = Guid.Parse("33333333-3333-3333-3333-333333333333");
    public AppDbContext Db { get; } = new(new DbContextOptionsBuilder<AppDbContext>()
        .UseInMemoryDatabase(Guid.NewGuid().ToString()).Options);
    public MemoryReceiptStorage Storage { get; } = new();
    public PayHereSettings Settings { get; } = new() {
        MerchantId = "TEST123", MerchantSecret = "isolated-test-secret", Sandbox = true,
        NotifyUrl = "https://example.test/notify", FrontendBaseUrl = "http://localhost:3000", MaxAttempts = 3
    };
    public AppointmentPaymentService Payments { get; }
    public AppointmentOnlinePaymentService Online { get; }
    private readonly HttpClient doctorHttp = new(new DoctorHandler()) { BaseAddress = new Uri("https://example.test/") };

    public PaymentFixture()
    {
        var repository = new AppointmentPaymentRepository(Db);
        Payments = new(repository, new DoctorPaymentClient(doctorHttp, new HttpContextAccessor()), Storage, TimeProvider.System);
        Online = new(repository, new PayHerePaymentGateway(Options.Create(Settings), NullLogger<PayHerePaymentGateway>.Instance),
            Options.Create(Settings), TimeProvider.System);
        Db.Appointments.Add(new() {
            Id = 1, AppointmentReference = "CN-APT-TEST", PatientId = Patient,
            DoctorId = Guid.Parse("22222222-2222-2222-2222-222222222222"), DoctorName = "Dr Test",
            DoctorAvailabilitySlotId = 10, AppointmentStartUtc = DateTime.UtcNow.AddDays(1),
            AppointmentEndUtc = DateTime.UtcNow.AddDays(1).AddMinutes(30)
        });
        Db.SaveChanges();
    }
    public Task<AppointmentPaymentResponseDto> Select(string method) => Payments.SelectPaymentMethodAsync(Patient, 1, new() { Method = method });
    public Task<AppointmentOnlinePaymentSessionDto> Start() => Online.StartAsync(Patient, 1, Billing(), "http://localhost:3000");
    public static StartAppointmentOnlinePaymentDto Billing() => new() {
        FirstName = "Test", LastName = "Patient", Email = "patient@example.test", Phone = "0771234567", Address = "Test address", City = "Test city"
    };
    public static FormFile Receipt(byte[]? bytes = null, string type = "application/pdf", string name = "receipt.pdf")
    {
        bytes ??= Encoding.ASCII.GetBytes("%PDF-1.4\nGCN45 test receipt\n%%EOF");
        return new FormFile(new MemoryStream(bytes), 0, bytes.Length, "receipt", name) { Headers = new HeaderDictionary(), ContentType = type };
    }
    // Independent protocol fixture: never use the production signature helper to sign test inputs.
    public Dictionary<string, string> Notification(string orderId, string amount = "2700.00", string currency = "LKR", string status = "2")
    {
        static string Hash(string value) => Convert.ToHexString(MD5.HashData(Encoding.UTF8.GetBytes(value)));
        return new() {
            ["merchant_id"] = "TEST123", ["order_id"] = orderId, ["payhere_amount"] = amount,
            ["payhere_currency"] = currency, ["status_code"] = status, ["payment_id"] = "TEST-TRANSACTION",
            ["md5sig"] = Hash("TEST123" + orderId + amount + currency + status + Hash("isolated-test-secret"))
        };
    }
    public void Dispose() { Db.Dispose(); doctorHttp.Dispose(); }
    internal sealed class DoctorHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) {
                Content = JsonContent.Create(new { doctorId = "22222222-2222-2222-2222-222222222222", fullName = "Dr Test", consultationFee = 2700m,
                    availability = new { hasAvailableSlots = true, availableSlotCount = 1 }, upcomingSlots = Array.Empty<object>() })
            });
    }
}

internal sealed class MemoryReceiptStorage : IBlobStorageService
{
    public Dictionary<string, byte[]> Files { get; } = [];
    public bool FailUploads { get; set; }
    public async Task<BlobUploadResult> UploadReceiptAsync(Stream stream, string fileName, string contentType, CancellationToken cancellationToken = default)
    {
        if (FailUploads) throw new IOException("Simulated receipt storage outage");
        using var buffer = new MemoryStream(); await stream.CopyToAsync(buffer, cancellationToken);
        var name = Guid.NewGuid().ToString("N"); Files.Add(name, buffer.ToArray());
        return new() { BlobName = name, ContainerName = "private-test-receipts" };
    }
    public Task DeleteAsync(string blobName, CancellationToken cancellationToken = default) { Files.Remove(blobName); return Task.CompletedTask; }
    public Task<BlobDownloadResult> DownloadReceiptAsync(string blobName, CancellationToken cancellationToken = default) =>
        Task.FromResult(new BlobDownloadResult { Content = new MemoryStream(Files[blobName]), ContentType = "application/pdf" });
}
