using System.Net;
using System.Net.Http.Json;
using System.Security.Claims;
using System.Text.Encodings.Web;
using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.DTOs.Appointment;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AppointmentIntegration.Api.Tests.Integration;

public class AppointmentsControllerIntegrationTests
{
    private WebApplicationFactory<Program> CreateFactory()
    {
        return new WebApplicationFactory<Program>()
            .WithWebHostBuilder(builder =>
            {
                builder.ConfigureServices(services =>
                {
                    services.RemoveAll<DbContextOptions<AppDbContext>>();
                    services.RemoveAll<AppDbContext>();

                    services.AddDbContext<AppDbContext>(options =>
                    {
                        options.UseInMemoryDatabase(
                            $"AppointmentTests-{Guid.NewGuid()}");
                    });

                    services.AddAuthentication("Test")
                        .AddScheme<AuthenticationSchemeOptions, TestAuthHandler>(
                            "Test",
                            _ => { });

                    services.AddAuthorization();
                });
            });
    }

    [Fact]
    public async Task Post_WithoutAuthentication_ReturnsUnauthorized()
    {
        await using var factory = CreateFactory();
        var client = factory.CreateClient();

        var request = new BookAppointmentRequestDto
        {
            DoctorId = Guid.NewGuid(),
            SlotId = 1
        };

        var response = await client.PostAsJsonAsync(
            "/api/appointments",
            request);

        Assert.Equal(
            HttpStatusCode.Unauthorized,
            response.StatusCode);
    }

    [Fact]
    public async Task Post_MissingDoctorAndSlot_ReturnsBadRequest()
    {
        await using var factory = CreateFactory();

        var client = factory.CreateClient();
        client.DefaultRequestHeaders.Add("X-Test-Auth", "true");

        var request = new BookAppointmentRequestDto
        {
            DoctorId = Guid.Empty,
            SlotId = 0
        };

        var response = await client.PostAsJsonAsync(
            "/api/appointments",
            request);

        Assert.Equal(
            HttpStatusCode.BadRequest,
            response.StatusCode);
    }

    private sealed class TestAuthHandler
        : AuthenticationHandler<AuthenticationSchemeOptions>
    {
        public TestAuthHandler(
            IOptionsMonitor<AuthenticationSchemeOptions> options,
            ILoggerFactory logger,
            UrlEncoder encoder)
            : base(options, logger, encoder)
        {
        }

        protected override Task<AuthenticateResult> HandleAuthenticateAsync()
        {
            if (!Request.Headers.ContainsKey("X-Test-Auth"))
            {
                return Task.FromResult(
                    AuthenticateResult.NoResult());
            }

            var claims = new[]
            {
                new Claim(
                    ClaimTypes.NameIdentifier,
                    "11111111-1111-1111-1111-111111111111")
            };

            var identity = new ClaimsIdentity(
                claims,
                "Test");

            var principal = new ClaimsPrincipal(identity);

            var ticket = new AuthenticationTicket(
                principal,
                "Test");

            return Task.FromResult(
                AuthenticateResult.Success(ticket));
        }
    }
}