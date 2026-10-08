using System.IdentityModel.Tokens.Jwt;
using System.Net.Http.Headers;
using System.Security.Claims;
using System.Text;
using AppointmentIntegration.Api.Data;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.IdentityModel.Tokens;
namespace AppointmentIntegration.Api.Tests.Integration;

public class PublicInformationFactory(bool failSaves = false, string? remoteAddress = null) : WebApplicationFactory<Program>
{
    private const string Secret = "gcn50-isolated-test-secret-at-least-32-characters";
    private readonly string database = Guid.NewGuid().ToString();
    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Testing");
        builder.ConfigureAppConfiguration((_, config) => config.AddInMemoryCollection(new Dictionary<string, string?> {
            ["JwtSettings:Secret"] = Secret, ["JwtSettings:Issuer"] = "TestIssuer", ["JwtSettings:Audience"] = "TestAudience"
        }));
        builder.ConfigureServices(services => {
            if (remoteAddress is not null) services.AddSingleton<IStartupFilter>(new RemoteAddressFilter(remoteAddress));
            services.RemoveAll<DbContextOptions<AppDbContext>>();
            foreach (var descriptor in services.Where(d => d.ServiceType.FullName?.StartsWith("Microsoft.EntityFrameworkCore.Infrastructure.IDbContextOptionsConfiguration") == true).ToArray()) services.Remove(descriptor);
            services.AddDbContext<AppDbContext>(options => {
                options.UseInMemoryDatabase(database);
                if (failSaves) options.AddInterceptors(new FailedSaveInterceptor());
            });
        });
    }
    private sealed class RemoteAddressFilter(string address) : IStartupFilter
    {
        public Action<Microsoft.AspNetCore.Builder.IApplicationBuilder> Configure(Action<Microsoft.AspNetCore.Builder.IApplicationBuilder> next) => app => {
            app.Use(async (context, following) => { context.Connection.RemoteIpAddress = System.Net.IPAddress.Parse(address); await following(); });
            next(app);
        };
    }
    public HttpClient Client(string? role = null)
    {
        var client = CreateClient();
        if (role is not null) {
            var token = new JwtSecurityToken("TestIssuer", "TestAudience", [new(ClaimTypes.NameIdentifier, Guid.NewGuid().ToString()), new(ClaimTypes.Role, role)],
                expires: DateTime.UtcNow.AddMinutes(5), signingCredentials: new(new SymmetricSecurityKey(Encoding.UTF8.GetBytes(Secret)), SecurityAlgorithms.HmacSha256));
            client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", new JwtSecurityTokenHandler().WriteToken(token));
        }
        return client;
    }
    private sealed class FailedSaveInterceptor : Microsoft.EntityFrameworkCore.Diagnostics.SaveChangesInterceptor
    {
        public override ValueTask<Microsoft.EntityFrameworkCore.Diagnostics.InterceptionResult<int>> SavingChangesAsync(
            Microsoft.EntityFrameworkCore.Diagnostics.DbContextEventData eventData,
            Microsoft.EntityFrameworkCore.Diagnostics.InterceptionResult<int> result, CancellationToken cancellationToken = default) =>
                throw new DbUpdateException("Simulated storage failure");
    }
}
