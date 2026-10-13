using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
namespace AppointmentIntegration.Api.Tests.Integration;
public class PharmacyImageTests
{
    [Fact]
    public async Task ValidPhotoIsServedPubliclyAndCanBePublishedByAdmin()
    {
        using var factory = new PublicInformationFactory();
        using var admin = factory.Client("Admin");
        using var upload = new MultipartFormDataContent();
        upload.Add(new ByteArrayContent(Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j1ioAAAAASUVORK5CYII=")), "file", "photo.png");
        var result = await admin.PostAsync("/api/admin/pharmacy-information/images", upload);
        Assert.Equal(HttpStatusCode.OK, result.StatusCode);
        var image = await result.Content.ReadFromJsonAsync<JsonElement>();
        var url = image.GetProperty("url").GetString()!;
        using var visitor = factory.Client();
        Assert.Equal(HttpStatusCode.OK, (await visitor.GetAsync(url)).StatusCode);
        var information = await admin.GetFromJsonAsync<AppointmentIntegration.Api.DTOs.PublicContent.PharmacyInformationDto>("/api/admin/pharmacy-information");
        information!.Images = [new(url, "Test photograph")];
        Assert.Equal(HttpStatusCode.OK, (await admin.PutAsJsonAsync("/api/admin/pharmacy-information", information)).StatusCode);
    }
    [Theory]
    [InlineData("Patient")]
    [InlineData("Doctor")]
    [InlineData("PharmacyStaff")]
    public async Task NonAdminCannotUploadPhotographs(string role)
    {
        using var factory = new PublicInformationFactory();
        using var client = factory.Client(role);
        using var form = new MultipartFormDataContent();
        Assert.Equal(HttpStatusCode.Forbidden, (await client.PostAsync("/api/admin/pharmacy-information/images", form)).StatusCode);
    }
    [Fact]
    public async Task ImageUploadRequiresAdminAndRejectsInvalidFiles()
    {
        using var factory = new PublicInformationFactory();
        using var visitor = factory.Client();
        using var empty = new MultipartFormDataContent();
        Assert.Equal(HttpStatusCode.Unauthorized, (await visitor.PostAsync("/api/admin/pharmacy-information/images", empty)).StatusCode);
        using var admin = factory.Client("Admin");
        using var invalid = new MultipartFormDataContent();
        invalid.Add(new ByteArrayContent([1, 2, 3]), "file", "fake.png");
        Assert.Equal(HttpStatusCode.BadRequest, (await admin.PostAsync("/api/admin/pharmacy-information/images", invalid)).StatusCode);
    }
}
