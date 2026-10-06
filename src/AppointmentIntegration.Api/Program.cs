using System.Text;
using AppointmentIntegration.Api.Clients;
using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.DTOs.Appointment;
using AppointmentIntegration.Api.Repositories;
using AppointmentIntegration.Api.Services;
using AppointmentIntegration.Api.Services.Interfaces;
using AppointmentIntegration.Api.Validators;
using FluentValidation;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();

builder.Services.AddCors(options =>
{
    options.AddPolicy("FrontendPolicy", policy =>
    {
        policy
            .WithOrigins("http://localhost:3000")
            .AllowAnyHeader()
            .AllowAnyMethod();
    });
});

builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var connectionString =
    builder.Configuration.GetConnectionString("DefaultConnection");

if (!string.IsNullOrWhiteSpace(connectionString))
{
    builder.Services.AddDbContext<AppDbContext>(options =>
        options.UseMySql(
            connectionString,
            ServerVersion.AutoDetect(connectionString)));
}

builder.Services.AddHttpContextAccessor();

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

builder.Services.AddScoped<IAppointmentRepository, AppointmentRepository>();
builder.Services.AddScoped<IAppointmentBookingService, AppointmentBookingService>();

builder.Services.AddScoped<
    IValidator<BookAppointmentRequestDto>,
    BookAppointmentValidator>();

builder.Services.AddSingleton(TimeProvider.System);

var jwtSecret =
    builder.Configuration["JwtSettings:Secret"];

var jwtIssuer =
    builder.Configuration["JwtSettings:Issuer"];

var jwtAudience =
    builder.Configuration["JwtSettings:Audience"];

if (!string.IsNullOrWhiteSpace(jwtSecret))
{
    builder.Services
        .AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
        .AddJwtBearer(options =>
        {
            options.TokenValidationParameters =
                new TokenValidationParameters
                {
                    ValidateIssuer = true,
                    ValidateAudience = true,
                    ValidateLifetime = true,
                    ValidateIssuerSigningKey = true,

                    ValidIssuer = jwtIssuer,
                    ValidAudience = jwtAudience,

                    IssuerSigningKey =
                        new SymmetricSecurityKey(
                            Encoding.UTF8.GetBytes(jwtSecret))
                };
        });
}

builder.Services.AddAuthorization();

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseHttpsRedirection();

app.UseCors("FrontendPolicy");

app.UseAuthentication();
app.UseAuthorization();

app.MapControllers();

app.Run();

public partial class Program
{
}