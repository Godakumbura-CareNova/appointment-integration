using System.Net;
using System.Net.Http.Json;
using System.Security.Claims;
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
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AppointmentIntegration.Api.Tests.Integration;

// GCN-45 QA additions. HTTP-level checks through WebApplicationFactory with an isolated in-memory database,
// a stubbed doctor service, in-memory receipt storage and test PayHere settings. No real payment or network call.
public class AppointmentPaymentsQaGcn45Tests
{
    private const string Online = "/api/appointments/1/payment/online";

    [Fact]
    public async Task X1_OtherPatientOrInvalidIdentityCannotUseTheOnlinePaymentEndpoints()
    {
        using var factory = new QaFactory(); await factory.Seed();
        using var owner = factory.Client("Patient"); using var stranger = factory.Client("Patient", Guid.NewGuid().ToString());
        using var badIdentity = factory.Client("Patient", "not-a-guid"); using var visitor = factory.Client();
        await owner.PostAsJsonAsync("/api/appointments/1/payment/method", new { method = "PaymentGateway" });
        var started = await owner.PostAsJsonAsync($"{Online}/start", PaymentFixture.Billing());
        Assert.Equal(HttpStatusCode.OK, started.StatusCode);
        var attemptId = (await started.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("attemptId").GetInt32();

        Assert.Equal(HttpStatusCode.NotFound, (await stranger.PostAsJsonAsync($"{Online}/start", PaymentFixture.Billing())).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await stranger.GetAsync($"{Online}/{attemptId}")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await stranger.PostAsync($"{Online}/{attemptId}/cancel", null)).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await visitor.GetAsync($"{Online}/{attemptId}")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await badIdentity.GetAsync("/api/appointments/1/payment")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await badIdentity.PostAsJsonAsync($"{Online}/start", PaymentFixture.Billing())).StatusCode);

        using var scope = factory.Services.CreateScope(); var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        var attempt = await db.AppointmentOnlinePaymentAttempts.SingleAsync();
        Assert.Equal(AppointmentOnlinePaymentAttemptStatus.Pending, attempt.Status);
        Assert.Equal(PaymentFixture.Patient, attempt.PatientId);
    }

    [Fact]
    public async Task X2_MaximumAttemptLimitIsEnforcedOverHttpWithAConflictAndNoExtraAttempt()
    {
        using var factory = new QaFactory(); await factory.Seed();
        using var patient = factory.Client("Patient"); using var gateway = factory.Client();
        await patient.PostAsJsonAsync("/api/appointments/1/payment/method", new { method = "PaymentGateway" });
        for (var i = 1; i <= 3; i++)
        {
            var start = await patient.PostAsJsonAsync($"{Online}/start", PaymentFixture.Billing());
            Assert.Equal(HttpStatusCode.OK, start.StatusCode);
            var order = (await start.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("gatewayOrderId").GetString()!;
            using var signer = new PaymentFixture();
            Assert.Equal(HttpStatusCode.OK, (await gateway.PostAsync("/api/appointment-payments/payhere/notify",
                new FormUrlEncodedContent(signer.Notification(order, status: "-2")))).StatusCode);
        }
        var fourth = await patient.PostAsJsonAsync($"{Online}/start", PaymentFixture.Billing());
        Assert.Equal(HttpStatusCode.Conflict, fourth.StatusCode);
        Assert.Contains("maximum of 3 attempts", await fourth.Content.ReadAsStringAsync());
        using var scope = factory.Services.CreateScope(); var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        Assert.Equal(3, await db.AppointmentOnlinePaymentAttempts.CountAsync());
        Assert.NotEqual(AppointmentPaymentStatus.Successful, (await db.AppointmentPayments.SingleAsync()).Status);
    }

    [Fact]
    public async Task X3_OnlyThePharmacyStaffRoleCanReviewReceipts()
    {
        using var factory = new QaFactory(); await factory.Seed();
        const string list = "/api/staff/appointment-payments/receipts";
        const string verify = "/api/staff/appointment-payments/appointments/1/receipt/verify";
        using (var visitor = factory.Client()) Assert.Equal(HttpStatusCode.Unauthorized, (await visitor.GetAsync(list)).StatusCode);
        foreach (var role in new[] { "Patient", "Doctor", "Admin" })
        {
            using var other = factory.Client(role);
            Assert.Equal(HttpStatusCode.Forbidden, (await other.GetAsync(list)).StatusCode);
            Assert.Equal(HttpStatusCode.Forbidden, (await other.PostAsJsonAsync(verify, new { approved = true })).StatusCode);
        }
        using (var staff = factory.Client("PharmacyStaff"))
        {
            Assert.Equal(HttpStatusCode.OK, (await staff.GetAsync(list)).StatusCode);
            // Authorized staff pass the policy and reach the service, which has no payment to review here (404, not 401/403).
            Assert.Equal(HttpStatusCode.NotFound, (await staff.PostAsJsonAsync(verify, new { approved = false })).StatusCode);
        }
    }

    [Fact]
    public async Task X4_InvalidMethodsFeesAndBillingAreRejectedWithoutSavingPaymentData()
    {
        using var factory = new QaFactory(); await factory.Seed(); using var patient = factory.Client("Patient");
        const string method = "/api/appointments/1/payment/method";
        foreach (var invalid in new[] { "", "   ", "Crypto", "99" })
        {
            var rejected = await patient.PostAsJsonAsync(method, new { method = invalid });
            Assert.Equal(HttpStatusCode.BadRequest, rejected.StatusCode);
            Assert.Contains("Select a valid payment method", await rejected.Content.ReadAsStringAsync());
        }
        factory.Doctor.Fee = 0m;
        var noFee = await patient.PostAsJsonAsync(method, new { method = "Cash" });
        Assert.Equal(HttpStatusCode.Conflict, noFee.StatusCode);
        Assert.Contains("consultation fee has not been configured", await noFee.Content.ReadAsStringAsync());
        using (var scope = factory.Services.CreateScope())
            Assert.Empty(scope.ServiceProvider.GetRequiredService<AppDbContext>().AppointmentPayments);

        factory.Doctor.Fee = 2700m;
        Assert.Equal(HttpStatusCode.OK, (await patient.PostAsJsonAsync(method, new { method = "Cash" })).StatusCode);
        var notSelected = await patient.PostAsJsonAsync($"{Online}/start", PaymentFixture.Billing());
        Assert.Equal(HttpStatusCode.Conflict, notSelected.StatusCode);
        Assert.Contains("not the selected payment method", await notSelected.Content.ReadAsStringAsync());

        Assert.Equal(HttpStatusCode.OK, (await patient.PostAsJsonAsync(method, new { method = "PaymentGateway" })).StatusCode);
        var billing = PaymentFixture.Billing(); billing.Email = "not-an-email";
        var badBilling = await patient.PostAsJsonAsync($"{Online}/start", billing);
        Assert.Equal(HttpStatusCode.BadRequest, badBilling.StatusCode);
        Assert.Contains("Enter a valid email address.", await badBilling.Content.ReadAsStringAsync());

        using var check = factory.Services.CreateScope(); var db = check.ServiceProvider.GetRequiredService<AppDbContext>();
        Assert.Empty(db.AppointmentOnlinePaymentAttempts);
        var payment = await db.AppointmentPayments.SingleAsync();
        Assert.Equal(AppointmentPaymentMethod.PaymentGateway, payment.Method); Assert.Equal(2700m, payment.Amount);
    }

    private sealed class FeeDoctor : HttpMessageHandler
    {
        public decimal Fee { get; set; } = 2700m;
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) {
                Content = JsonContent.Create(new { doctorId = "22222222-2222-2222-2222-222222222222", fullName = "Dr Test", consultationFee = Fee,
                    availability = new { hasAvailableSlots = true, availableSlotCount = 1 }, upcomingSlots = Array.Empty<object>() })
            });
    }

    private sealed class QaFactory : WebApplicationFactory<Program>
    {
        private readonly string database = Guid.NewGuid().ToString();
        public FeeDoctor Doctor { get; } = new();
        protected override void ConfigureWebHost(IWebHostBuilder builder)
        {
            builder.UseEnvironment("Testing");
            builder.ConfigureAppConfiguration((_, config) => config.AddInMemoryCollection(new Dictionary<string, string?> {
                ["ConnectionStrings:DefaultConnection"] = "", ["JwtSettings:Secret"] = ""
            }));
            builder.ConfigureServices(services => {
                services.RemoveAll<AppDbContext>(); services.RemoveAll<DbContextOptions<AppDbContext>>();
                foreach (var d in services.Where(x => x.ServiceType.FullName?.StartsWith("Microsoft.EntityFrameworkCore.Infrastructure.IDbContextOptionsConfiguration") == true).ToArray()) services.Remove(d);
                services.AddDbContext<AppDbContext>(o => o.UseInMemoryDatabase(database));
                services.AddHttpClient<DoctorPaymentClient>(c => c.BaseAddress = new Uri("https://example.test/"))
                    .ConfigurePrimaryHttpMessageHandler(() => Doctor);
                services.RemoveAll<IBlobStorageService>(); services.AddSingleton<IBlobStorageService>(new MemoryReceiptStorage());
                services.PostConfigure<PayHereSettings>(s => {
                    s.MerchantId = "TEST123"; s.MerchantSecret = "isolated-test-secret"; s.Sandbox = true; s.AllowLivePayments = false;
                    s.NotifyUrl = "https://example.test/notify"; s.FrontendBaseUrl = "http://localhost:3000"; s.MaxAttempts = 3;
                });
                services.AddAuthentication(o => { o.DefaultAuthenticateScheme = "QaTests"; o.DefaultChallengeScheme = "QaTests"; o.DefaultForbidScheme = "QaTests"; })
                    .AddScheme<AuthenticationSchemeOptions, QaIdentity>("QaTests", _ => { });
            });
        }
        public async Task Seed()
        {
            using var scope = Services.CreateScope(); var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
            db.Appointments.Add(new() { Id = 1, PatientId = PaymentFixture.Patient, AppointmentReference = "CN-APT-TEST", DoctorName = "Dr Test",
                DoctorId = Guid.Parse("22222222-2222-2222-2222-222222222222"), DoctorAvailabilitySlotId = 10 });
            await db.SaveChangesAsync();
        }
        public HttpClient Client(string? role = null, string? subject = null)
        {
            var client = CreateClient();
            if (role is not null) { client.DefaultRequestHeaders.Add("X-Test-Role", role); client.DefaultRequestHeaders.Add("X-Test-Subject", subject ?? PaymentFixture.Patient.ToString()); }
            return client;
        }
    }

    private sealed class QaIdentity(IOptionsMonitor<AuthenticationSchemeOptions> options, ILoggerFactory logger, UrlEncoder encoder)
        : AuthenticationHandler<AuthenticationSchemeOptions>(options, logger, encoder)
    {
        protected override Task<AuthenticateResult> HandleAuthenticateAsync()
        {
            if (!Request.Headers.TryGetValue("X-Test-Role", out var role)) return Task.FromResult(AuthenticateResult.NoResult());
            var identity = new ClaimsIdentity([new(ClaimTypes.Role, role.ToString()), new(ClaimTypes.NameIdentifier, Request.Headers["X-Test-Subject"].ToString())], "QaTests");
            return Task.FromResult(AuthenticateResult.Success(new AuthenticationTicket(new ClaimsPrincipal(identity), "QaTests")));
        }
    }
}
