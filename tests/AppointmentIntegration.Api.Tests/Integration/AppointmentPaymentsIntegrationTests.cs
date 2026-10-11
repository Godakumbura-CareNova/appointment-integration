using System.Net;
using System.Net.Http.Json;
using System.Security.Claims;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using AppointmentIntegration.Api.Clients;
using AppointmentIntegration.Api.Config;
using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Models;
using AppointmentIntegration.Api.Services.Interfaces;
using AppointmentIntegration.Api.Tests.Support;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AppointmentIntegration.Api.Tests.Integration;

public class AppointmentPaymentsIntegrationTests
{
    [Theory]
    [InlineData("Cash", "Pending")]
    [InlineData("BankTransfer", "AwaitingBankTransferReceipt")]
    [InlineData("PaymentGateway", "AwaitingGatewayPayment")]
    public async Task PatientMethodSelectionSurvivesANewRequest(string method, string status)
    {
        using var factory = new PaymentApiFactory(); await factory.Seed();
        using var patient = factory.Client("Patient");
        Assert.Equal(HttpStatusCode.OK, (await patient.PostAsJsonAsync("/api/appointments/1/payment/method", new { method })).StatusCode);
        var saved = await patient.GetFromJsonAsync<JsonElement>("/api/appointments/1/payment");
        Assert.Equal(method, saved.GetProperty("method").GetString()); Assert.Equal(status, saved.GetProperty("status").GetString());
        Assert.Equal(2700m, saved.GetProperty("amount").GetDecimal()); Assert.Equal("CN-APT-TEST", saved.GetProperty("appointmentReference").GetString());
    }

    [Fact]
    public async Task ReceiptSubmissionIsPrivateAndOnlyStaffCanConfirmPayment()
    {
        using var factory = new PaymentApiFactory(); await factory.Seed();
        using var patient = factory.Client("Patient"); using var staff = factory.Client("PharmacyStaff"); using var visitor = factory.Client();
        await patient.PostAsJsonAsync("/api/appointments/1/payment/method", new { method = "BankTransfer" });
        using var form = ReceiptForm();
        Assert.Equal(HttpStatusCode.OK, (await patient.PostAsync("/api/appointments/1/payment/receipt", form)).StatusCode);
        var pending = await staff.GetFromJsonAsync<JsonElement>("/api/staff/appointment-payments/receipts");
        var receiptId = Assert.Single(pending.EnumerateArray()).GetProperty("id").GetInt32();
        var filePath = $"/api/staff/appointment-payments/receipts/{receiptId}/file";
        Assert.Equal(HttpStatusCode.Unauthorized, (await visitor.GetAsync(filePath)).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await patient.GetAsync(filePath)).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await staff.GetAsync(filePath)).StatusCode);
        const string review = "/api/staff/appointment-payments/appointments/1/receipt/verify";
        Assert.Equal(HttpStatusCode.Forbidden, (await patient.PostAsJsonAsync(review, new { approved = true })).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await staff.PostAsJsonAsync(review, new { approved = true })).StatusCode);
        var payment = await patient.GetFromJsonAsync<JsonElement>("/api/appointments/1/payment");
        Assert.Equal("Successful", payment.GetProperty("status").GetString());
        using (var scope = factory.Services.CreateScope())
        {
            var stored = await scope.ServiceProvider.GetRequiredService<AppDbContext>().AppointmentPayments.SingleAsync();
            Assert.NotNull(stored.ConfirmedAtUtc);
        }
        Assert.Empty((await staff.GetFromJsonAsync<JsonElement>("/api/staff/appointment-payments/receipts")).EnumerateArray());
    }

    [Fact]
    public async Task UnauthorizedAndOtherPatientRequestsCannotAccessOrChangePayment()
    {
        using var factory = new PaymentApiFactory(); await factory.Seed();
        using var patient = factory.Client("Patient"); using var stranger = factory.Client("Patient", Guid.NewGuid()); using var visitor = factory.Client();
        await patient.PostAsJsonAsync("/api/appointments/1/payment/method", new { method = "BankTransfer" });
        Assert.Equal(HttpStatusCode.Unauthorized, (await visitor.GetAsync("/api/appointments/1/payment")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await stranger.GetAsync("/api/appointments/1/payment")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await stranger.PostAsJsonAsync("/api/appointments/1/payment/method", new { method = "Cash" })).StatusCode);
        using var form = ReceiptForm();
        Assert.Equal(HttpStatusCode.NotFound, (await stranger.PostAsync("/api/appointments/1/payment/receipt", form)).StatusCode);
        using var scope = factory.Services.CreateScope(); Assert.Empty(scope.ServiceProvider.GetRequiredService<AppDbContext>().AppointmentReceipts);
    }

    [Fact]
    public async Task SignedNotificationIsRequiredForOnlineConfirmation()
    {
        using var factory = new PaymentApiFactory(); await factory.Seed();
        using var patient = factory.Client("Patient"); using var gateway = factory.Client();
        await patient.PostAsJsonAsync("/api/appointments/1/payment/method", new { method = "PaymentGateway" });
        var start = await patient.PostAsJsonAsync("/api/appointments/1/payment/online/start", PaymentFixture.Billing());
        Assert.Equal(HttpStatusCode.OK, start.StatusCode);
        var session = await start.Content.ReadFromJsonAsync<JsonElement>(); var orderId = session.GetProperty("gatewayOrderId").GetString()!;
        using var signatureFixture = new PaymentFixture(); var callback = signatureFixture.Notification(orderId);
        var forged = new Dictionary<string, string>(callback) { ["md5sig"] = new string('0', 32) };
        Assert.Equal(HttpStatusCode.BadRequest, (await gateway.PostAsync("/api/appointment-payments/payhere/notify", new FormUrlEncodedContent(forged))).StatusCode);
        var before = await patient.GetFromJsonAsync<JsonElement>("/api/appointments/1/payment");
        Assert.Equal("AwaitingGatewayPayment", before.GetProperty("status").GetString());
        Assert.Equal(HttpStatusCode.OK, (await gateway.PostAsync("/api/appointment-payments/payhere/notify", new FormUrlEncodedContent(callback))).StatusCode);
        var result = await patient.GetFromJsonAsync<JsonElement>($"/api/appointments/1/payment/online/{session.GetProperty("attemptId").GetInt32()}");
        Assert.Equal("Succeeded", result.GetProperty("outcome").GetString()); Assert.False(result.GetProperty("canRetry").GetBoolean());
        Assert.Equal("Successful", result.GetProperty("payment").GetProperty("status").GetString());
    }

    [Fact]
    public async Task InvalidReceiptReturnsValidationErrorWithoutCreatingAReview()
    {
        using var factory = new PaymentApiFactory(); await factory.Seed(); using var patient = factory.Client("Patient");
        await patient.PostAsJsonAsync("/api/appointments/1/payment/method", new { method = "BankTransfer" });
        using var form = new MultipartFormDataContent(); var file = new ByteArrayContent([1, 2, 3]);
        file.Headers.ContentType = new("application/pdf"); form.Add(file, "receipt", "receipt.pdf");
        Assert.Equal(HttpStatusCode.BadRequest, (await patient.PostAsync("/api/appointments/1/payment/receipt", form)).StatusCode);
        using var scope = factory.Services.CreateScope(); Assert.Empty(scope.ServiceProvider.GetRequiredService<AppDbContext>().AppointmentReceipts);
    }

    private static MultipartFormDataContent ReceiptForm()
    {
        var form = new MultipartFormDataContent(); var file = new ByteArrayContent(Encoding.ASCII.GetBytes("%PDF-1.4\nTest receipt\n%%EOF"));
        file.Headers.ContentType = new("application/pdf"); form.Add(file, "receipt", "receipt.pdf"); return form;
    }

    internal sealed class PaymentApiFactory : WebApplicationFactory<Program>
    {
        private readonly string database = Guid.NewGuid().ToString();
        private readonly SqliteConnection? connection;
        public PaymentApiFactory(bool relational = false)
        {
            if (relational) { connection = new SqliteConnection("Data Source=:memory:"); connection.Open(); }
        }
        protected override void Dispose(bool disposing)
        {
            base.Dispose(disposing);
            if (disposing) connection?.Dispose();
        }
        protected override void ConfigureWebHost(IWebHostBuilder builder)
        {
            builder.UseEnvironment("Testing");
            builder.ConfigureAppConfiguration((_, config) => config.AddInMemoryCollection(new Dictionary<string, string?> {
                ["ConnectionStrings:DefaultConnection"] = "", ["JwtSettings:Secret"] = ""
            }));
            builder.ConfigureServices(services => {
                services.RemoveAll<AppDbContext>(); services.RemoveAll<DbContextOptions<AppDbContext>>();
                foreach (var descriptor in services.Where(x => x.ServiceType.FullName?.StartsWith("Microsoft.EntityFrameworkCore.Infrastructure.IDbContextOptionsConfiguration") == true).ToArray()) services.Remove(descriptor);
                services.AddDbContext<AppDbContext>(options => {
                    if (connection is null) options.UseInMemoryDatabase(database);
                    else options.UseSqlite(connection);
                });
                services.AddHttpClient<DoctorPaymentClient>(client => client.BaseAddress = new Uri("https://example.test/"))
                    .ConfigurePrimaryHttpMessageHandler(() => new PaymentFixture.DoctorHandler());
                services.RemoveAll<IBlobStorageService>(); services.AddSingleton<IBlobStorageService>(new MemoryReceiptStorage());
                services.PostConfigure<PayHereSettings>(settings => {
                    settings.MerchantId = "TEST123"; settings.MerchantSecret = "isolated-test-secret"; settings.Sandbox = true;
                    settings.AllowLivePayments = false; settings.NotifyUrl = "https://example.test/notify"; settings.FrontendBaseUrl = "http://localhost:3000";
                });
                services.AddAuthentication(options => { options.DefaultAuthenticateScheme = "PaymentTests"; options.DefaultChallengeScheme = "PaymentTests"; options.DefaultForbidScheme = "PaymentTests"; })
                    .AddScheme<AuthenticationSchemeOptions, TestIdentity>("PaymentTests", _ => { });
            });
        }
        public async Task Seed()
        {
            using var scope = Services.CreateScope(); var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
            await db.Database.EnsureCreatedAsync();
            db.Appointments.Add(new() { Id = 1, PatientId = PaymentFixture.Patient, AppointmentReference = "CN-APT-TEST", DoctorName = "Dr Test",
                DoctorId = Guid.Parse("22222222-2222-2222-2222-222222222222"), DoctorAvailabilitySlotId = 10 });
            await db.SaveChangesAsync();
        }
        public HttpClient Client(string? role = null, Guid? id = null)
        {
            var client = CreateClient();
            if (role is not null) { client.DefaultRequestHeaders.Add("X-Test-Role", role); client.DefaultRequestHeaders.Add("X-Test-Patient", (id ?? PaymentFixture.Patient).ToString()); }
            return client;
        }
    }
    private sealed class TestIdentity(IOptionsMonitor<AuthenticationSchemeOptions> options, ILoggerFactory logger, UrlEncoder encoder)
        : AuthenticationHandler<AuthenticationSchemeOptions>(options, logger, encoder)
    {
        protected override Task<AuthenticateResult> HandleAuthenticateAsync()
        {
            if (!Request.Headers.TryGetValue("X-Test-Role", out var role)) return Task.FromResult(AuthenticateResult.NoResult());
            var identity = new ClaimsIdentity([new(ClaimTypes.Role, role.ToString()), new(ClaimTypes.NameIdentifier, Request.Headers["X-Test-Patient"].ToString())], "PaymentTests");
            return Task.FromResult(AuthenticateResult.Success(new AuthenticationTicket(new ClaimsPrincipal(identity), "PaymentTests")));
        }
    }
}
