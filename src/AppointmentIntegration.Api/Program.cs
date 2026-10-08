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

var builder = WebApplication.CreateBuilder(args);
builder.Configuration.AddJsonFile("publiccontent.json", optional: false, reloadOnChange: true);
// Environment and command-line settings override the public-content defaults.
builder.Configuration.AddEnvironmentVariables();
builder.Configuration.AddCommandLine(args);

// Add services to the container.

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

var app = builder.Build();
app.UseForwardedHeaders();
Directory.CreateDirectory(Path.Combine(app.Environment.ContentRootPath, "wwwroot", "uploads", "pharmacy-information"));

// Configure the HTTP request pipeline.
if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseHttpsRedirection();

app.UseCors("PublicFrontend");
app.Use(async (context, next) => {
    try { await next(); }
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

app.MapControllers();

app.Run();
public partial class Program { }
