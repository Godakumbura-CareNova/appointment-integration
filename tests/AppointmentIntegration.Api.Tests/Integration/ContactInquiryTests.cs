using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
namespace AppointmentIntegration.Api.Tests.Integration;
public class ContactInquiryTests
{
    [Theory]
    [InlineData("127.0.0.1", true)]
    [InlineData("203.0.113.10", false)]
    public async Task TrustedProxyPreservesSeparateClientLimitsButUntrustedHeadersCannotBypassLimits(string address, bool trusted)
    {
        using var factory = new PublicInformationFactory(remoteAddress: address);
        using var client = factory.Client();
        client.DefaultRequestHeaders.Add("X-Forwarded-For", "198.51.100.1");
        for (var i = 0; i < 5; i++) Assert.Equal(HttpStatusCode.BadRequest, (await client.PostAsJsonAsync("/api/public/contact-inquiries", new { })).StatusCode);
        client.DefaultRequestHeaders.Remove("X-Forwarded-For");
        client.DefaultRequestHeaders.Add("X-Forwarded-For", "198.51.100.2");
        Assert.Equal(trusted ? HttpStatusCode.BadRequest : HttpStatusCode.TooManyRequests, (await client.PostAsJsonAsync("/api/public/contact-inquiries", new { })).StatusCode);
    }
    [Fact]
    public async Task StorageFailureDoesNotConfirmOrPersistAnInquiry()
    {
        using var factory = new PublicInformationFactory(failSaves: true);
        using var visitor = factory.Client();
        Assert.Equal(HttpStatusCode.ServiceUnavailable, (await visitor.PostAsJsonAsync("/api/public/contact-inquiries", new { name = "Visitor", email = "visitor@example.test", subject = "Inquiry", message = "Please help", phone = "" })).StatusCode);
        using var admin = factory.Client("Admin");
        var list = await admin.GetFromJsonAsync<JsonElement>("/api/admin/contact-inquiries");
        Assert.Equal(0, list.GetProperty("totalCount").GetInt32());
    }
    [Theory]
    [InlineData("Patient")]
    [InlineData("Doctor")]
    [InlineData("PharmacyStaff")]
    public async Task NonAdminsCannotReadOrReviewInquiries(string role)
    {
        using var factory = new PublicInformationFactory();
        using var client = factory.Client(role);
        Assert.Equal(HttpStatusCode.Forbidden, (await client.GetAsync("/api/admin/contact-inquiries")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await client.PatchAsync($"/api/admin/contact-inquiries/{Guid.NewGuid()}/reviewed", null)).StatusCode);
    }
    [Fact]
    public async Task VisitorCanSubmitButOnlyAdminCanReadAndReview()
    {
        using var factory = new PublicInformationFactory();
        using var visitor = factory.Client();
        var response = await visitor.PostAsJsonAsync("/api/public/contact-inquiries", new { name = "Visitor", email = "visitor@example.test", phone = "", subject = "Opening hours", message = "Please confirm your opening hours." });
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var body = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.False(body.TryGetProperty("email", out _));
        Assert.Equal(HttpStatusCode.Unauthorized, (await visitor.GetAsync("/api/admin/contact-inquiries")).StatusCode);
        using var admin = factory.Client("Admin");
        var list = await admin.GetFromJsonAsync<JsonElement>("/api/admin/contact-inquiries");
        Assert.Single(list.GetProperty("items").EnumerateArray());
        Assert.Equal("Opening hours", list.GetProperty("items")[0].GetProperty("subject").GetString());
        Assert.Equal(HttpStatusCode.OK, (await admin.PatchAsync($"/api/admin/contact-inquiries/{body.GetProperty("id").GetString()}/reviewed", null)).StatusCode);
    }
    [Fact]
    public async Task InvalidInquiryDoesNotSaveAndRequestsAreRateLimited()
    {
        using var factory = new PublicInformationFactory();
        using var visitor = factory.Client();
        for (var i = 0; i < 5; i++) Assert.Equal(HttpStatusCode.BadRequest, (await visitor.PostAsJsonAsync("/api/public/contact-inquiries", new { name = " ", email = "wrong", subject = "", message = "", phone = "abc" })).StatusCode);
        Assert.Equal(HttpStatusCode.TooManyRequests, (await visitor.PostAsJsonAsync("/api/public/contact-inquiries", new { })).StatusCode);
        using var admin = factory.Client("Admin");
        var list = await admin.GetFromJsonAsync<JsonElement>("/api/admin/contact-inquiries");
        Assert.Equal(0, list.GetProperty("totalCount").GetInt32());
    }
}
