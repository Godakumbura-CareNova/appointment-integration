using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Configuration;
using AppointmentIntegration.Api.Services;

namespace AppointmentIntegration.Api.Tests.Integration;
public class PublicHomeTests
{
    [Fact]
    public async Task MissingDatabaseConfigurationRetainsConfiguredHomeAndFeaturedContent()
    {
        using var factory = new WebApplicationFactory<Program>().WithWebHostBuilder(builder => {
            builder.UseEnvironment("Testing");
            builder.ConfigureAppConfiguration((_, configuration) => configuration.AddInMemoryCollection(
                new Dictionary<string, string?> { ["ConnectionStrings:DefaultConnection"] = "" }));
            builder.ConfigureServices(services => services.AddHttpClient("PublicContent")
                .ConfigurePrimaryHttpMessageHandler(() => new MixedHandler()));
        });
        using var client = factory.CreateClient();
        var response = await client.GetAsync("/api/public/home");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var home = await response.Content.ReadFromJsonAsync<HomePageResponse>();
        Assert.Contains("CareNova", home!.Introduction);
        Assert.NotEmpty(home.Services);
        Assert.Equal("Vitamin C", Assert.Single(home.FeaturedMedicines).GetProperty("name").GetString());
        Assert.Single(home.SectionErrors);
    }
    private sealed class SlowInformation : AppointmentIntegration.Api.Services.Interfaces.IPharmacyInformationReader
    {
        public async Task<AppointmentIntegration.Api.DTOs.PublicContent.PharmacyInformationDto> GetAsync(CancellationToken token)
        {
            await Task.Delay(TimeSpan.FromSeconds(5), token);
            return new() { Introduction = "Too late" };
        }
    }
    [Fact]
    public async Task SlowInformationStorageDoesNotDelayConfiguredHomeFallback()
    {
        using var factory = new WebApplicationFactory<Program>().WithWebHostBuilder(builder => builder.ConfigureServices(services => {
            services.AddSingleton<AppointmentIntegration.Api.Services.Interfaces.IPharmacyInformationReader>(new SlowInformation());
            services.AddHttpClient("PublicContent").ConfigurePrimaryHttpMessageHandler(() => new UnavailableHandler());
        }));
        using var client = factory.CreateClient();
        var clock = System.Diagnostics.Stopwatch.StartNew();
        var home = await client.GetFromJsonAsync<HomePageResponse>("/api/public/home");
        Assert.Contains("CareNova", home!.Introduction);
        Assert.True(clock.Elapsed < TimeSpan.FromSeconds(4), "Optional database lookup delayed the home response.");
    }
    private sealed class UnavailableHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.ServiceUnavailable));
    }
    [Fact]
    public async Task AnonymousVisitorGetsIntroductionWhenUpstreamServicesFail()
    {
        using var factory = new WebApplicationFactory<Program>().WithWebHostBuilder(builder =>
            builder.ConfigureServices(services => services.AddHttpClient("PublicContent").ConfigurePrimaryHttpMessageHandler(() => new UnavailableHandler())));
        using var client = factory.CreateClient();
        var response = await client.GetAsync("/api/public/home");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var home = await response.Content.ReadFromJsonAsync<HomePageResponse>();
        Assert.NotNull(home);
        Assert.Contains("CareNova", home.Introduction);
        Assert.NotEmpty(home.Services);
        Assert.Equal(3, home.Services.Count);
        Assert.Equal(2, home.SectionErrors.Count);
        Assert.Empty(home.FeaturedMedicines);
    }
    private sealed class MixedHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            var isMedicine = request.RequestUri!.AbsolutePath.Contains("medicines");
            return Task.FromResult(new HttpResponseMessage(isMedicine ? HttpStatusCode.OK : HttpStatusCode.ServiceUnavailable)
            {
                Content = new StringContent("{\"items\":[{\"id\":1,\"name\":\"Vitamin C\",\"price\":200}]}", System.Text.Encoding.UTF8, "application/json")
            });
        }
    }
    [Fact]
    public async Task DoctorFailureRetainsLiveMedicineResults()
    {
        using var factory = new WebApplicationFactory<Program>().WithWebHostBuilder(builder =>
            builder.ConfigureServices(services => services.AddHttpClient("PublicContent").ConfigurePrimaryHttpMessageHandler(() => new MixedHandler())));
        using var client = factory.CreateClient();
        var home = await client.GetFromJsonAsync<HomePageResponse>("/api/public/home");
        Assert.Equal("Vitamin C", Assert.Single(home!.FeaturedMedicines).GetProperty("name").GetString());
        Assert.Single(home.SectionErrors);
        Assert.Contains("doctors", home.SectionErrors[0]);
    }
    private sealed class FeaturedHandler : HttpMessageHandler
    {
        private int active;
        public int MaxConcurrent;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            if (request.RequestUri!.AbsolutePath.Contains("medicines/"))
            {
                var count = Interlocked.Increment(ref active);
                lock (this) MaxConcurrent = Math.Max(MaxConcurrent, count);
                await Task.Delay(100, token);
                Interlocked.Decrement(ref active);
                return new(HttpStatusCode.OK) { Content = new StringContent("{\"id\":1,\"name\":\"Vitamin C\"}", System.Text.Encoding.UTF8, "application/json") };
            }
            return new(HttpStatusCode.OK) { Content = new StringContent("{\"items\":[]}", System.Text.Encoding.UTF8, "application/json") };
        }
    }
    [Fact]
    public async Task ConfiguredFeaturedItemsLoadConcurrentlyWithinOneTimeoutWindow()
    {
        var handler = new FeaturedHandler();
        using var factory = new WebApplicationFactory<Program>().WithWebHostBuilder(builder =>
        {
            for (var i = 0; i < 4; i++) builder.UseSetting($"PublicContent:FeaturedMedicineIds:{i}", (i + 1).ToString());
            builder.ConfigureServices(services => services.AddHttpClient("PublicContent").ConfigurePrimaryHttpMessageHandler(() => handler));
        });
        using var client = factory.CreateClient();
        var home = await client.GetFromJsonAsync<HomePageResponse>("/api/public/home");
        Assert.Equal(4, home!.FeaturedMedicines.Count);
        Assert.Equal(4, handler.MaxConcurrent);
    }
}
