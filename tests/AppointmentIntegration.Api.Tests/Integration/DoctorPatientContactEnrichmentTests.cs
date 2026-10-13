using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Http;

namespace AppointmentIntegration.Api.Tests.Integration;

public class DoctorPatientContactEnrichmentTests
{
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public async Task ContactServiceSuccessEnrichesAndFailurePreservesAppointments(bool fail)
    {
        using var factory = new AppointmentPaymentsIntegrationTests.PaymentApiFactory(true); await factory.Seed();
        using var enriched = factory.WithWebHostBuilder(builder => builder.ConfigureServices(services => {
            services.ConfigureAll<HttpClientFactoryOptions>(options => {
                options.HttpClientActions.Add(client => client.BaseAddress = new Uri("https://auth.test/"));
                options.HttpMessageHandlerBuilderActions.Add(b => b.PrimaryHandler = new ContactHandler(fail));
            });
        }));
        using var client = enriched.CreateClient(); client.DefaultRequestHeaders.Add("X-Test-Role", "Doctor"); client.DefaultRequestHeaders.Add("X-Test-Patient", DoctorAppointmentsIntegrationTests.Doctor.ToString()); client.DefaultRequestHeaders.Authorization = new("Bearer", "isolated-token");
        var result = await client.GetFromJsonAsync<JsonElement>("/api/doctor/appointments");
        var appointment = Assert.Single(result.GetProperty("appointments").EnumerateArray());
        Assert.Equal(fail, result.GetProperty("contactsUnavailable").GetBoolean());
        if (!fail) { Assert.Equal("Test Patient", appointment.GetProperty("patientName").GetString()); Assert.Equal("0771234567", appointment.GetProperty("patientPhone").GetString()); }
        else Assert.Equal(JsonValueKind.Null, appointment.GetProperty("patientName").ValueKind);
    }
    sealed class ContactHandler(bool fail) : HttpMessageHandler
    {
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Assert.Equal("Bearer isolated-token", request.Headers.Authorization?.ToString());
            Assert.Equal("/api/doctor/patient-contacts", request.RequestUri!.AbsolutePath);
            var body = await request.Content!.ReadFromJsonAsync<JsonElement>(cancellationToken: ct);
            var id = Assert.Single(body.GetProperty("patientIds").EnumerateArray()).GetGuid();
            return fail ? new(HttpStatusCode.ServiceUnavailable) : new(HttpStatusCode.OK) { Content = JsonContent.Create(new[] { new { patientId = id, fullName = "Test Patient", mobileNumber = "0771234567" } }) };
        }
    }
}
