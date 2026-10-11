using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using AppointmentIntegration.Api.Services;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;

namespace AppointmentIntegration.Api.Tests.Integration;

// GCN-49 QA: five focused tests for GET /api/public/home. They add to (and do not repeat) PublicHomeTests, which already
// covers "both upstreams answer 503", "doctors fail but medicines survive" and "featured items load concurrently".
// Upstream pharmacy and doctor services are replaced by in-process stubs; no network, database or secret is involved.
public class Gcn49PublicHomeQaTests
{
    private const string Home = "/api/public/home";

    private sealed class StubHandler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> respond) : HttpMessageHandler
    {
        public int Calls;
        public readonly List<string> Paths = new();
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            Interlocked.Increment(ref Calls);
            lock (Paths) Paths.Add(request.RequestUri!.PathAndQuery);
            return await respond(request, token);
        }
    }

    private static WebApplicationFactory<Program> Host(StubHandler handler, params (string Key, string Value)[] settings) =>
        new WebApplicationFactory<Program>().WithWebHostBuilder(builder =>
        {
            foreach (var (key, value) in settings) builder.UseSetting(key, value);
            builder.ConfigureServices(services => services.AddHttpClient("PublicContent").ConfigurePrimaryHttpMessageHandler(() => handler));
        });

    private static Task<HttpResponseMessage> Json(string body, HttpStatusCode status = HttpStatusCode.OK) =>
        Task.FromResult(new HttpResponseMessage(status) { Content = new StringContent(body, Encoding.UTF8, "application/json") });

    private static string Items(string kind, int count) =>
        "{\"items\":[" + string.Join(",", Enumerable.Range(1, count).Select(i => kind == "medicines"
            ? $"{{\"id\":{i},\"name\":\"Medicine {i}\",\"price\":{i * 100}}}"
            : $"{{\"doctorId\":\"00000000-0000-0000-0000-{i:000000000000}\",\"fullName\":\"Doctor {i}\"}}")) + "]}";

    // 1. Response structure the frontend relies on, with healthy upstreams, plus the "at most 4 featured items" limit
    [Fact]
    public async Task HealthyHomeResponseHasTheExactContractAndNeverMoreThanFourFeaturedItems()
    {
        var handler = new StubHandler((request, _) => Json(Items(request.RequestUri!.AbsolutePath.Contains("medicines") ? "medicines" : "doctors", 6)));
        using var factory = Host(handler);
        using var client = factory.CreateClient();

        var response = await client.GetAsync(Home);
        var text = await response.Content.ReadAsStringAsync();
        using var document = JsonDocument.Parse(text);
        var root = document.RootElement;

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("application/json", response.Content.Headers.ContentType?.MediaType);
        Assert.Equal(new[] { "featuredDoctors", "featuredMedicines", "introduction", "notices", "sectionErrors", "services" }, root.EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal));
        Assert.False(string.IsNullOrWhiteSpace(root.GetProperty("introduction").GetString()));
        Assert.All(root.GetProperty("services").EnumerateArray(), s => { Assert.False(string.IsNullOrWhiteSpace(s.GetProperty("title").GetString())); Assert.False(string.IsNullOrWhiteSpace(s.GetProperty("description").GetString())); });
        Assert.All(root.GetProperty("notices").EnumerateArray(), n => { Assert.False(string.IsNullOrWhiteSpace(n.GetProperty("title").GetString())); Assert.False(string.IsNullOrWhiteSpace(n.GetProperty("message").GetString())); });
        Assert.Equal(0, root.GetProperty("sectionErrors").GetArrayLength());
        Assert.Equal(new[] { 1, 2, 3, 4 }, root.GetProperty("featuredMedicines").EnumerateArray().Select(m => m.GetProperty("id").GetInt32()));
        Assert.Equal(4, root.GetProperty("featuredDoctors").GetArrayLength());
        Assert.Equal(2, handler.Calls); // one list request per section, nothing more

        // more than four configured featured ids: still at most four are requested and returned
        var selected = new StubHandler((request, _) => Json("{\"id\":1,\"name\":\"Vitamin C\"}"));
        using var configured = Host(selected, Enumerable.Range(0, 6).Select(i => ($"PublicContent:FeaturedMedicineIds:{i}", (i + 1).ToString())).Append(("PublicContent:FeaturedDoctorIds:0", Guid.NewGuid().ToString())).ToArray());
        using var configuredClient = configured.CreateClient();
        var many = await configuredClient.GetFromJsonAsync<HomePageResponse>(Home);
        Assert.Equal(4, many!.FeaturedMedicines.Count);
        Assert.Equal(5, selected.Calls); // 4 medicines (limit) + 1 doctor
    }

    // 2. A hanging upstream must be cut off at the 5 second client timeout, concurrently, and the page must still answer
    [Fact]
    public async Task HangingUpstreamsAreCutOffAtTheTimeoutAndTheHomePageStillAnswers()
    {
        var handler = new StubHandler(async (_, token) => { await Task.Delay(Timeout.Infinite, token); return new HttpResponseMessage(HttpStatusCode.OK); });
        using var factory = Host(handler);
        using var client = factory.CreateClient();
        client.Timeout = TimeSpan.FromSeconds(30);

        var clock = Stopwatch.StartNew();
        var response = await client.GetAsync(Home);
        clock.Stop();
        var home = await response.Content.ReadFromJsonAsync<HomePageResponse>();

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.InRange(clock.Elapsed.TotalSeconds, 4.0, 8.0); // timed out (about 5 s), not instantly failed and not 2 x 5 s
        Assert.Equal(2, handler.Calls);
        Assert.Equal(2, home!.SectionErrors.Count);
        Assert.Equal(3, home.Services.Count);
        Assert.NotEmpty(home.Notices);
        Assert.False(string.IsNullOrWhiteSpace(home.Introduction));
        Assert.Empty(home.FeaturedMedicines);
        Assert.Empty(home.FeaturedDoctors);
    }

    // 3. Anonymous visitors, unsupported methods and cross-origin policy
    [Fact]
    public async Task HomeIsOpenToAnonymousVisitorsOnlyViaGetAndOnlyForTheConfiguredOrigin()
    {
        using var factory = Host(new StubHandler((_, _) => Json("{\"items\":[]}")));
        using var client = factory.CreateClient();

        var anonymous = await client.GetAsync(Home);
        using var withBadToken = new HttpRequestMessage(HttpMethod.Get, Home) { Headers = { Authorization = new AuthenticationHeaderValue("Bearer", "not-a-real-token") } };
        var badToken = await client.SendAsync(withBadToken);
        var post = await client.PostAsJsonAsync(Home, new { });
        using var allowed = new HttpRequestMessage(HttpMethod.Get, Home) { Headers = { { "Origin", "http://localhost:3000" } } };
        var allowedOrigin = await client.SendAsync(allowed);
        using var foreign = new HttpRequestMessage(HttpMethod.Get, Home) { Headers = { { "Origin", "http://evil.example" } } };
        var foreignOrigin = await client.SendAsync(foreign);
        using var preflight = new HttpRequestMessage(HttpMethod.Options, Home) { Headers = { { "Origin", "http://localhost:3000" }, { "Access-Control-Request-Method", "GET" } } };
        var allowedPreflight = await client.SendAsync(preflight);

        Assert.Equal(HttpStatusCode.OK, anonymous.StatusCode);
        Assert.Equal(HttpStatusCode.OK, badToken.StatusCode); // no credentials are required or inspected
        Assert.False(anonymous.Headers.Contains("WWW-Authenticate"));
        Assert.False(anonymous.Headers.Contains("Set-Cookie"), "anonymous visitors must not be given a cookie");
        Assert.Equal(HttpStatusCode.MethodNotAllowed, post.StatusCode);
        Assert.Equal("http://localhost:3000", allowedOrigin.Headers.GetValues("Access-Control-Allow-Origin").Single());
        Assert.False(foreignOrigin.Headers.Contains("Access-Control-Allow-Origin"), "an unrelated website must not be granted cross-origin access");
        Assert.True(allowedPreflight.IsSuccessStatusCode);
        Assert.Equal("http://localhost:3000", allowedPreflight.Headers.GetValues("Access-Control-Allow-Origin").Single());
    }

    // 4. Whatever an upstream answers, one bad section must degrade to a section error, never take the whole page down
    [Fact]
    public async Task UnexpectedUpstreamJsonShapesDegradeOneSectionInsteadOfBreakingTheHomePage()
    {
        string medicineBody = "";
        var handler = new StubHandler((request, _) => request.RequestUri!.AbsolutePath.Contains("medicines")
            ? Json(medicineBody) : Json(Items("doctors", 2)));
        using var factory = Host(handler);
        using var client = factory.CreateClient();
        var shapes = new[]
        {
            ("object without items", "{\"data\":[]}"), ("items is a string", "{\"items\":\"nope\"}"), ("items is null", "{\"items\":null}"),
            ("not JSON at all", "<html><body>Bad gateway</body></html>"), ("empty body", ""),
            ("JSON array at the root", "[{\"id\":1,\"name\":\"Vitamin C\"}]"), ("JSON number at the root", "42"), ("JSON string at the root", "\"text\""), ("JSON true at the root", "true"),
        };

        var broken = new List<string>();
        foreach (var (label, body) in shapes)
        {
            medicineBody = body;
            var response = await client.GetAsync(Home);
            var text = await response.Content.ReadAsStringAsync();
            if (response.StatusCode != HttpStatusCode.OK) { broken.Add($"{label}: the WHOLE page answered HTTP {(int)response.StatusCode} ({text})"); continue; }
            var home = JsonSerializer.Deserialize<HomePageResponse>(text, new JsonSerializerOptions(JsonSerializerDefaults.Web))!;
            if (home.SectionErrors.Count != 1 || !home.SectionErrors[0].Contains("medicines")) broken.Add($"{label}: expected exactly one 'medicines' section error but got [{string.Join(" | ", home.SectionErrors)}]");
            if (home.FeaturedDoctors.Count != 2) broken.Add($"{label}: the healthy doctors section was lost");
            if (home.Services.Count != 3) broken.Add($"{label}: the configured services were lost");
            if (text.Contains("Bad gateway")) broken.Add($"{label}: upstream response text leaked to the visitor");
        }

        Assert.True(broken.Count == 0, "These upstream answers broke the home page:" + Environment.NewLine + string.Join(Environment.NewLine, broken));
    }

    // 5. Failures must not be sticky: every request reflects the CURRENT upstream state (retry works), including thrown connection errors
    [Fact]
    public async Task EveryRequestReflectsTheCurrentUpstreamStateSoRetryRecoversWithoutStaleErrors()
    {
        var healthy = false;
        var handler = new StubHandler((request, _) => healthy
            ? Json(Items(request.RequestUri!.AbsolutePath.Contains("medicines") ? "medicines" : "doctors", 2))
            : throw new HttpRequestException("Connection refused"));
        using var factory = Host(handler);
        using var client = factory.CreateClient();

        async Task<HomePageResponse> Fetch() { var r = await client.GetAsync(Home); Assert.Equal(HttpStatusCode.OK, r.StatusCode); return (await r.Content.ReadFromJsonAsync<HomePageResponse>())!; }

        var down = await Fetch();
        Assert.Equal(2, down.SectionErrors.Count);
        Assert.Empty(down.FeaturedMedicines);
        Assert.Equal(2, handler.Calls);

        healthy = true;
        var recovered = await Fetch();
        Assert.Empty(recovered.SectionErrors);
        Assert.Equal(2, recovered.FeaturedMedicines.Count);
        Assert.Equal(2, recovered.FeaturedDoctors.Count);
        Assert.Equal(4, handler.Calls); // fresh upstream calls, not a cached failure

        healthy = false;
        var downAgain = await Fetch();
        Assert.Equal(2, downAgain.SectionErrors.Count);
        Assert.Empty(downAgain.FeaturedDoctors); // no stale items served once the upstream is down again
        Assert.Equal(6, handler.Calls);
    }
}
