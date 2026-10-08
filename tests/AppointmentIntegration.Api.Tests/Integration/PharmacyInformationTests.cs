using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Mvc.Testing;

namespace AppointmentIntegration.Api.Tests.Integration;

public class PharmacyInformationTests
{
    [Fact]
    public async Task InformationStorageFailureIsAnErrorRatherThanAnEditConflict()
    {
        using var factory = new PublicInformationFactory(failSaves: true);
        using var admin = factory.Client("Admin");
        var content = await admin.GetFromJsonAsync<AppointmentIntegration.Api.DTOs.PublicContent.PharmacyInformationDto>("/api/admin/pharmacy-information");
        Assert.Equal(HttpStatusCode.ServiceUnavailable, (await admin.PutAsJsonAsync("/api/admin/pharmacy-information", content)).StatusCode);
    }
    [Theory]
    [InlineData("https://evil.example/maps/embed")]
    [InlineData("javascript:alert(1)")]
    [InlineData("https://www.google.com/maps/embed-not-a-map")]
    public async Task InvalidMapSourcesAreRejected(string map)
    {
        using var factory = new PublicInformationFactory();
        using var admin = factory.Client("Admin");
        var content = await admin.GetFromJsonAsync<AppointmentIntegration.Api.DTOs.PublicContent.PharmacyInformationDto>("/api/admin/pharmacy-information");
        content!.MapEmbedUrl = map;
        Assert.Equal(HttpStatusCode.BadRequest, (await admin.PutAsJsonAsync("/api/admin/pharmacy-information", content)).StatusCode);
    }
    [Fact]
    public async Task PublicInformationEndpointExistsAndAdminEditingRequiresAuthentication()
    {
        using var factory = new PublicInformationFactory();
        using var client = factory.CreateClient();
        Assert.Equal(HttpStatusCode.OK, (await client.GetAsync("/api/public/pharmacy-information")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await client.GetAsync("/api/admin/pharmacy-information")).StatusCode);
    }

    [Theory]
    [InlineData("Patient")]
    [InlineData("Doctor")]
    [InlineData("PharmacyStaff")]
    public async Task OtherRolesCanReadButCannotEdit(string role)
    {
        using var factory = new PublicInformationFactory();
        using var client = factory.Client(role);
        Assert.Equal(HttpStatusCode.OK, (await client.GetAsync("/api/public/pharmacy-information")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await client.GetAsync("/api/admin/pharmacy-information")).StatusCode);
    }

    [Fact]
    public async Task AdminSavePersistsAndRejectsAStaleRevision()
    {
        using var factory = new PublicInformationFactory();
        using var admin = factory.Client("Admin");
        var content = await admin.GetFromJsonAsync<AppointmentIntegration.Api.DTOs.PublicContent.PharmacyInformationDto>("/api/admin/pharmacy-information");
        Assert.Empty(content!.Phone);
        Assert.Empty(content.Images);
        content.Mission = "Improve access to pharmacy services";
        Assert.Equal(HttpStatusCode.OK, (await admin.PutAsJsonAsync("/api/admin/pharmacy-information", content)).StatusCode);
        using var visitor = factory.Client();
        var saved = await visitor.GetFromJsonAsync<AppointmentIntegration.Api.DTOs.PublicContent.PharmacyInformationDto>("/api/public/pharmacy-information");
        Assert.Equal(content.Mission, saved!.Mission);
        Assert.NotEqual(Guid.Empty, saved.Revision);
        Assert.Equal(HttpStatusCode.Conflict, (await admin.PutAsJsonAsync("/api/admin/pharmacy-information", content)).StatusCode);
        saved.Email = "invalid email";
        Assert.Equal(HttpStatusCode.BadRequest, (await admin.PutAsJsonAsync("/api/admin/pharmacy-information", saved)).StatusCode);
    }
}
