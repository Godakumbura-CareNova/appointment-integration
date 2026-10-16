using System.Text;
using System.Threading.RateLimiting;
using AppointmentIntegration.Api.Config;
using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Services;
using AppointmentIntegration.Api.Validators;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using Microsoft.AspNetCore.HttpOverrides;
using Prometheus;
using AppointmentIntegration.Api.Clients;
using AppointmentIntegration.Api.DTOs.Appointment;
using AppointmentIntegration.Api.Repositories;
using AppointmentIntegration.Api.Services.Interfaces;
using FluentValidation;
using AppointmentIntegration.Api.Security;

var builder = WebApplication.CreateBuilder(args);
builder.Configuration.AddJsonFile("publiccontent.json", optional: false, reloadOnChange: true);
// Environment and command-line settings override the public-content defaults.
builder.Configuration.AddEnvironmentVariables();
builder.Configuration.AddCommandLine(args);

builder.Services.AddControllers();
builder.Services.Configure<ForwardedHeadersOptions>(options => {
    options.ForwardedHeaders = ForwardedHeaders.XForwardedFor;
    options.KnownProxies.Add(System.Net.IPAddress.Loopback);
    foreach (var address in builder.Configuration.GetSection("PublicContent:TrustedProxyAddresses").Get<string[]>() ?? []) {
        if (!System.Net.IPAddress.TryParse(address, out var proxy)) throw new InvalidOperationException("Trusted proxy addresses must be IP addresses.");
        options.KnownProxies.Add(proxy);
    }
});
builder.Services.AddDbContext<AppDbContext>(options => options.UseMySql(
    builder.Configuration.GetConnectionString("DefaultConnection") ?? "",
    new MySqlServerVersion(new Version(8, 0, 0))));
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme).AddJwtBearer();
builder.Services.AddOptions<JwtBearerOptions>(JwtBearerDefaults.AuthenticationScheme).Configure<IConfiguration>((options, configuration) => {
    var jwt = configuration.GetSection("JwtSettings").Get<JwtSettings>() ?? new();
    options.TokenValidationParameters = new() {
        ValidateIssuer = true, ValidateAudience = true, ValidateLifetime = true, ValidateIssuerSigningKey = true,
        ValidIssuer = jwt.Issuer, ValidAudience = jwt.Audience, ClockSkew = TimeSpan.Zero,
        IssuerSigningKey = string.IsNullOrWhiteSpace(jwt.Secret) ? null : new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwt.Secret))
    };
    options.Events = new() { OnMessageReceived = context => {
        if (string.IsNullOrWhiteSpace(jwt.Secret)) context.Fail("JWT authentication is not configured.");
        return Task.CompletedTask;
    }};
});
builder.Services.AddAuthorization(options => options.AddPolicy("Admin", policy => policy.RequireAuthenticatedUser().RequireRole("Admin")));
builder.Services.AddScoped<PharmacyInformationService>();
builder.Services.AddScoped<AppointmentIntegration.Api.Services.Interfaces.IPharmacyInformationReader>(services => services.GetRequiredService<PharmacyInformationService>());
// Resolve optional storage inside the homepage fallback, including configuration failures.
builder.Services.AddScoped(services => new Lazy<AppointmentIntegration.Api.Services.Interfaces.IPharmacyInformationReader>(
    () => services.GetRequiredService<AppointmentIntegration.Api.Services.Interfaces.IPharmacyInformationReader>()));
builder.Services.AddScoped<PharmacyInformationValidator>();
builder.Services.AddScoped<ContactInquiryService>();
builder.Services.AddScoped<ContactInquiryValidator>();
builder.Services.AddScoped<PharmacyImageService>();
builder.Services.AddRateLimiter(options => {
    options.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
    options.AddPolicy("Inquiries", context => RateLimitPartition.GetFixedWindowLimiter(
        context.Connection.RemoteIpAddress?.ToString() ?? "unknown", _ => new() {
            PermitLimit = 5, Window = TimeSpan.FromMinutes(1), QueueLimit = 0, AutoReplenishment = true
        }));
    options.OnRejected = async (context, token) => {
        context.HttpContext.Response.Headers.RetryAfter = "60";
        await context.HttpContext.Response.WriteAsJsonAsync(new { message = "Too many inquiries. Please wait a minute and try again." }, token);
    };
});
builder.Services.Configure<AppointmentIntegration.Api.Services.PublicContentOptions>(builder.Configuration.GetSection("PublicContent"));
builder.Services.AddHttpClient("PublicContent", client => client.Timeout = TimeSpan.FromSeconds(5));
builder.Services.AddScoped<AppointmentIntegration.Api.Services.PublicContentService>();
builder.Services.AddCors(options => options.AddPolicy("PublicFrontend", policy => policy
    .WithOrigins(builder.Configuration.GetSection("PublicContent:AllowedOrigins").Get<string[]>() ?? ["http://localhost:3000"])
    .AllowAnyHeader().AllowAnyMethod()));
// Learn more about configuring Swagger/OpenAPI at https://aka.ms/aspnetcore/swashbuckle
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

builder.Services.AddHttpContextAccessor();
builder.Services.AddScoped<IAppointmentMutationScope, AppointmentMutationScope>();
builder.Services.AddScoped<IAppointmentCancellationService, AppointmentCancellationService>();

builder.Services.AddHttpClient<DoctorPaymentClient>(client =>
{
    var baseUrl =
        builder.Configuration["DoctorPaymentService:BaseUrl"];

    if (!string.IsNullOrWhiteSpace(baseUrl))
    {
        client.BaseAddress = new Uri(
            baseUrl.TrimEnd('/') + "/");
    }
});

builder.Services.AddScoped<
    IAppointmentRepository,
    AppointmentRepository>();

builder.Services.AddScoped<
    IAppointmentPaymentRepository,
    AppointmentPaymentRepository>();

builder.Services.AddScoped<
    IAppointmentBookingService,
    AppointmentBookingService>();

builder.Services.AddScoped<
    IValidator<BookAppointmentRequestDto>,
    BookAppointmentValidator>();

builder.Services.AddScoped<
    IAppointmentPaymentService,
    AppointmentPaymentService>();

builder.Services.AddScoped<
    IAppointmentOnlinePaymentService,
    AppointmentOnlinePaymentService>();

builder.Services.AddScoped<
    IBlobStorageService,
    BlobStorageService>();    
    
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddScoped<AppointmentDashboardService>();
builder.Services.AddScoped<IPatientAppointmentService, PatientAppointmentService>();
builder.Services.AddScoped<IDoctorAppointmentService, DoctorAppointmentService>();
builder.Services.AddHttpClient<IUserAuthClient, UserAuthClient>(client => {
    if (Uri.TryCreate(builder.Configuration["UserAuthService:BaseUrl"], UriKind.Absolute, out var uri) && uri.Scheme is "http" or "https")
        client.BaseAddress = new Uri(uri.ToString().TrimEnd('/') + "/");
    client.Timeout = TimeSpan.FromSeconds(10);
}).ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler { AllowAutoRedirect = false });

builder.Services.AddOptions<PayHereSettings>()
    .Bind(builder.Configuration.GetSection("PayHere"));

builder.Services.AddSingleton<
    IAppointmentPaymentGateway,
    PayHerePaymentGateway>();

builder.Services.AddAuthorizationPolicies();
builder.Services.AddHealthChecks();

var app = builder.Build();
app.UseForwardedHeaders();
Directory.CreateDirectory(Path.Combine(app.Environment.ContentRootPath, "wwwroot", "uploads", "pharmacy-information"));

// Swagger UI is served in every environment so evaluators can use the deployed API documentation.
app.UseSwagger();
app.UseSwaggerUI();

app.UseHttpsRedirection();

app.UseCors("PublicFrontend");
app.Use(async (context, next) => {
    try { await next(); }
    catch (Microsoft.AspNetCore.Http.BadHttpRequestException badRequest) when (!context.Response.HasStarted) {
        // A client problem (e.g. body larger than [RequestSizeLimit] -> 413), not a server outage.
        app.Logger.LogWarning(badRequest, "Rejected a bad request with status {StatusCode}", badRequest.StatusCode);
        context.Response.StatusCode = badRequest.StatusCode;
        await context.Response.WriteAsJsonAsync(new {
            message = badRequest.StatusCode == StatusCodes.Status413PayloadTooLarge
                ? "Your request is too large. Please shorten it and try again."
                : "The request could not be read. Please check it and try again."
        });
    }
    catch (Exception exception) when (exception is not OperationCanceledException && !context.Response.HasStarted) {
        app.Logger.LogError(exception, "Public information operation failed");
        context.Response.StatusCode = StatusCodes.Status503ServiceUnavailable;
        await context.Response.WriteAsJsonAsync(new { message = "This service is temporarily unavailable. Please try again." });
    }
});
app.UseAuthentication();
app.UseStaticFiles();
app.UseAuthorization();
app.UseRateLimiter();
app.UseHttpMetrics();

app.MapControllers();
app.MapHealthChecks("/health");
app.MapMetrics();

app.Run();
public partial class Program { }
