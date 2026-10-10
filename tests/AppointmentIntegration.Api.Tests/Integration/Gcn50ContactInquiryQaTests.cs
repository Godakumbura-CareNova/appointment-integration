using System.IdentityModel.Tokens.Jwt;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Claims;
using System.Text;
using System.Text.Json;
using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Models;
using Microsoft.AspNetCore.Hosting;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.IdentityModel.Tokens;

namespace AppointmentIntegration.Api.Tests.Integration;

// GCN-50 QA: six focused tests. They add to (and do not repeat) ContactInquiryTests, which already covers the
// submit-list-review happy path, the 403 for Patient/Doctor/PharmacyStaff, rate limiting and a failing save.
public class Gcn50ContactInquiryQaTests
{
    private const string Submit = "/api/public/contact-inquiries";
    private const string Admin = "/api/admin/contact-inquiries";

    private static object Inquiry(string? name = null, string? email = null, string? phone = null, string? subject = null, string? message = null) => new
    {
        name = name ?? "QA Visitor", email = email ?? "qa.visitor@example.test", phone = phone ?? "+94 11 234 5678",
        subject = subject ?? "QA opening hours", message = message ?? "Please confirm your opening hours."
    };

    private static async Task<List<Guid>> Seed(PublicInformationFactory factory, int count)
    {
        using var scope = factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        var ids = new List<Guid>();
        for (var i = 0; i < count; i++)
        {
            ids.Add(Guid.NewGuid());
            db.ContactInquiries.Add(new ContactInquiry
            {
                Id = ids[i], Name = $"QA Visitor {i:00}", Email = $"qa{i:00}@example.test", Phone = "", Subject = $"Subject {i:00}", Message = $"Message {i:00}",
                SubmittedAtUtc = new DateTime(2026, 10, 1, 8, 0, 0, DateTimeKind.Utc).AddMinutes(i)
            });
        }
        await db.SaveChangesAsync();
        return ids;
    }

    // 1. Valid contact submission and persistence
    [Fact]
    public async Task ValidSubmissionIsPersistedTrimmedAndDoesNotEchoPersonalDetails()
    {
        using var factory = new PublicInformationFactory();
        using var visitor = factory.Client();

        var response = await visitor.PostAsJsonAsync(Submit, Inquiry(name: "  QA Visitor  ", subject: " Hours ", message: "  Please confirm.  ", phone: "+94112345678 "));

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var body = await response.Content.ReadFromJsonAsync<JsonElement>();
        var id = body.GetProperty("id").GetGuid();
        Assert.NotEqual(Guid.Empty, id);
        foreach (var personal in new[] { "name", "email", "phone", "subject" }) Assert.False(body.TryGetProperty(personal, out _), $"response must not echo {personal}");

        using var scope = factory.Services.CreateScope();
        var saved = await scope.ServiceProvider.GetRequiredService<AppDbContext>().ContactInquiries.AsNoTracking().SingleAsync();
        Assert.Equal(id, saved.Id);
        Assert.Equal(("QA Visitor", "qa.visitor@example.test", "+94112345678", "Hours", "Please confirm."), (saved.Name, saved.Email, saved.Phone, saved.Subject, saved.Message));
        Assert.Null(saved.ReviewedAtUtc);
        Assert.InRange(saved.SubmittedAtUtc, DateTime.UtcNow.AddMinutes(-1), DateTime.UtcNow.AddMinutes(1));
    }

    // 2. Invalid or missing required fields: nothing is saved and the visitor is told which fields are wrong
    [Fact]
    public async Task InvalidOrMissingFieldsAreRejectedWithFieldErrorsAndNothingIsSaved()
    {
        using var factory = new PublicInformationFactory();
        using var visitor = factory.Client();

        var empty = await visitor.PostAsJsonAsync(Submit, new { });
        var blank = await visitor.PostAsJsonAsync(Submit, Inquiry(name: "   ", subject: "   ", message: "   "));
        var badFormat = await visitor.PostAsJsonAsync(Submit, Inquiry(email: "not-an-email", phone: "call me"));
        var tooLong = await visitor.PostAsJsonAsync(Submit, Inquiry(message: new string('m', 5001)));

        foreach (var response in new[] { empty, blank, badFormat, tooLong }) Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        var emptyBody = await empty.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Please check your inquiry details.", emptyBody.GetProperty("message").GetString());
        foreach (var field in new[] { "Name", "Email", "Subject", "Message" }) Assert.True(emptyBody.GetProperty("errors").TryGetProperty(field, out _), field);
        var format = (await badFormat.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("errors");
        Assert.True(format.TryGetProperty("Email", out _) && format.TryGetProperty("Phone", out _));
        Assert.True((await tooLong.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("errors").TryGetProperty("Message", out _));
        using var scope = factory.Services.CreateScope();
        Assert.Equal(0, await scope.ServiceProvider.GetRequiredService<AppDbContext>().ContactInquiries.CountAsync());
    }

    // 3. Unauthorized access to admin endpoints (no inquiry data and no write access without a valid Admin token)
    [Fact]
    public async Task AdminEndpointsRejectAnonymousForgedExpiredAndNonAdminCallers()
    {
        using var factory = new PublicInformationFactory();
        var ids = await Seed(factory, 1);
        var endpoints = new (HttpMethod Method, string Url)[]
        {
            (HttpMethod.Get, Admin), (HttpMethod.Patch, $"{Admin}/{ids[0]}/reviewed"),
            (HttpMethod.Get, "/api/admin/pharmacy-information"), (HttpMethod.Put, "/api/admin/pharmacy-information"),
            (HttpMethod.Post, "/api/admin/pharmacy-information/images"),
        };
        HttpClient Forged(string secret, DateTime? expires = null)
        {
            var client = factory.CreateClient();
            var token = new JwtSecurityToken("TestIssuer", "TestAudience", [new(ClaimTypes.NameIdentifier, Guid.NewGuid().ToString()), new(ClaimTypes.Role, "Admin")],
                notBefore: expires?.AddMinutes(-10), expires: expires ?? DateTime.UtcNow.AddMinutes(5),
                signingCredentials: new(new SymmetricSecurityKey(Encoding.UTF8.GetBytes(secret)), SecurityAlgorithms.HmacSha256));
            client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", new JwtSecurityTokenHandler().WriteToken(token));
            return client;
        }

        using var anonymous = factory.CreateClient();
        using var forged = Forged("a-completely-different-secret-of-32+chars!!");
        using var expired = Forged("gcn50-isolated-test-secret-at-least-32-characters", DateTime.UtcNow.AddMinutes(-5));
        using var patient = factory.Client("Patient");
        foreach (var (client, expected) in new[] { (anonymous, HttpStatusCode.Unauthorized), (forged, HttpStatusCode.Unauthorized), (expired, HttpStatusCode.Unauthorized), (patient, HttpStatusCode.Forbidden) })
            foreach (var (method, url) in endpoints)
            {
                var response = await client.SendAsync(new HttpRequestMessage(method, url));
                Assert.True(response.StatusCode == expected, $"{method} {url} returned {(int)response.StatusCode}, expected {(int)expected}");
                Assert.DoesNotContain("example.test", await response.Content.ReadAsStringAsync());
            }

        using var scope = factory.Services.CreateScope();
        Assert.Null((await scope.ServiceProvider.GetRequiredService<AppDbContext>().ContactInquiries.AsNoTracking().SingleAsync()).ReviewedAtUtc);
    }

    // 4. Admin listing and pagination
    [Fact]
    public async Task AdminListsInquiriesNewestFirstWithCorrectPagesAndRejectsInvalidPaging()
    {
        using var factory = new PublicInformationFactory();
        await Seed(factory, 25);
        using var admin = factory.Client("Admin");

        var first = await admin.GetFromJsonAsync<JsonElement>($"{Admin}?page=1&pageSize=10");
        var last = await admin.GetFromJsonAsync<JsonElement>($"{Admin}?page=3&pageSize=10");
        var beyond = await admin.GetFromJsonAsync<JsonElement>($"{Admin}?page=4&pageSize=10");
        var defaults = await admin.GetFromJsonAsync<JsonElement>(Admin);

        Assert.Equal((10, 25, 3), (first.GetProperty("items").GetArrayLength(), first.GetProperty("totalCount").GetInt32(), first.GetProperty("totalPages").GetInt32()));
        Assert.Equal("Subject 24", first.GetProperty("items")[0].GetProperty("subject").GetString());
        Assert.Equal(5, last.GetProperty("items").GetArrayLength());
        Assert.Equal("Subject 00", last.GetProperty("items")[4].GetProperty("subject").GetString());
        Assert.Equal(0, beyond.GetProperty("items").GetArrayLength());
        Assert.Equal((1, 20, 20), (defaults.GetProperty("page").GetInt32(), defaults.GetProperty("pageSize").GetInt32(), defaults.GetProperty("items").GetArrayLength()));
        var seen = first.GetProperty("items").EnumerateArray().Select(x => x.GetProperty("id").GetGuid()).ToHashSet();
        Assert.DoesNotContain(last.GetProperty("items").EnumerateArray(), x => seen.Contains(x.GetProperty("id").GetGuid()));
        foreach (var bad in new[] { "page=0&pageSize=20", "page=-1&pageSize=20", "page=100001&pageSize=20", "page=1&pageSize=0", "page=1&pageSize=101", "page=abc" })
            Assert.Equal(HttpStatusCode.BadRequest, (await admin.GetAsync($"{Admin}?{bad}")).StatusCode);
    }

    // 5. Inquiry review behaviour
    [Fact]
    public async Task ReviewMarksOnlyThatInquiryKeepsTheFirstTimestampAndUnknownIdIs404()
    {
        using var factory = new PublicInformationFactory();
        var ids = await Seed(factory, 2);
        using var admin = factory.Client("Admin");

        var first = await admin.PatchAsync($"{Admin}/{ids[0]}/reviewed", null);
        var firstBody = await first.Content.ReadFromJsonAsync<JsonElement>();
        await Task.Delay(50);
        var again = await (await admin.PatchAsync($"{Admin}/{ids[0]}/reviewed", null)).Content.ReadFromJsonAsync<JsonElement>();
        var unknown = await admin.PatchAsync($"{Admin}/{Guid.NewGuid()}/reviewed", null);

        Assert.Equal(HttpStatusCode.OK, first.StatusCode);
        Assert.Equal(ids[0], firstBody.GetProperty("id").GetGuid());
        Assert.Equal(firstBody.GetProperty("reviewedAtUtc").GetDateTime(), again.GetProperty("reviewedAtUtc").GetDateTime());
        Assert.Equal(HttpStatusCode.NotFound, unknown.StatusCode);
        Assert.Equal("This inquiry is unavailable.", (await unknown.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("message").GetString());
        using var scope = factory.Services.CreateScope();
        var rows = await scope.ServiceProvider.GetRequiredService<AppDbContext>().ContactInquiries.AsNoTracking().ToDictionaryAsync(x => x.Id);
        Assert.NotNull(rows[ids[0]].ReviewedAtUtc);
        Assert.Null(rows[ids[1]].ReviewedAtUtc);
    }

    // 6. Database failure handling: a real unreachable database (nothing listens on port 1), not a simulated save error
    [Fact]
    public async Task UnreachableDatabaseReturns503WithoutConfirmingTheInquiryOrLeakingInternals()
    {
        using var factory = new UnavailableDatabaseFactory();
        using var visitor = factory.Client();
        using var admin = factory.Client("Admin");

        var submit = await visitor.PostAsJsonAsync(Submit, Inquiry());
        var list = await admin.GetAsync(Admin);
        var review = await admin.PatchAsync($"{Admin}/{Guid.NewGuid()}/reviewed", null);
        var invalid = await visitor.PostAsJsonAsync(Submit, new { });

        foreach (var response in new[] { submit, list, review }) Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        var text = await submit.Content.ReadAsStringAsync();
        Assert.Equal("This service is temporarily unavailable. Please try again.", JsonDocument.Parse(text).RootElement.GetProperty("message").GetString());
        Assert.DoesNotContain("received", text, StringComparison.OrdinalIgnoreCase);
        foreach (var internalDetail in new[] { "MySql", "127.0.0.1", "Exception", "   at " }) Assert.DoesNotContain(internalDetail, text);
        Assert.Equal(HttpStatusCode.BadRequest, invalid.StatusCode); // bad input is still reported as bad input
    }

    private sealed class UnavailableDatabaseFactory : PublicInformationFactory
    {
        protected override void ConfigureWebHost(IWebHostBuilder builder)
        {
            base.ConfigureWebHost(builder);
            builder.ConfigureServices(services =>
            {
                services.RemoveAll<DbContextOptions<AppDbContext>>();
                foreach (var descriptor in services.Where(d => d.ServiceType.FullName?.StartsWith("Microsoft.EntityFrameworkCore.Infrastructure.IDbContextOptionsConfiguration") == true).ToArray())
                    services.Remove(descriptor);
                services.AddDbContext<AppDbContext>(options => options.UseMySql(
                    "Server=127.0.0.1;Port=1;Database=unavailable;User=qa;Password=qa;Connection Timeout=2;", new MySqlServerVersion(new Version(8, 0, 0))));
            });
        }
    }
}
