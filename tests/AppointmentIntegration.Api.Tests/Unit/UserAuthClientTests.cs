using System.Net;
using AppointmentIntegration.Api.Clients;

namespace AppointmentIntegration.Api.Tests.Unit;

public class UserAuthClientTests
{
    [Theory]
    [InlineData(204, "")]
    [InlineData(200, "not json")]
    [InlineData(200, "{}")]
    [InlineData(200, "[{\"patientId\":\"99999999-9999-9999-9999-999999999999\",\"fullName\":\"Unexpected\",\"mobileNumber\":\"0771234567\"}]")]
    public async Task UnconfirmedOrUnexpectedContactsAreRejected(int code, string body)
    {
        using var http = new HttpClient(new ResponseHandler(code, body)) { BaseAddress = new Uri("https://auth.test/") };
        var client = new UserAuthClient(http);
        await Assert.ThrowsAnyAsync<Exception>(() => client.GetContactsAsync(new[] { Guid.Parse("11111111-1111-1111-1111-111111111111") }, "Bearer test-token", CancellationToken.None));
    }

    [Fact]
    public async Task CancellationCannotReturnContacts()
    {
        using var http = new HttpClient(new ResponseHandler(200, "[]")) { BaseAddress = new Uri("https://auth.test/") }; using var canceled = new CancellationTokenSource(); canceled.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => new UserAuthClient(http).GetContactsAsync(new[] { Guid.NewGuid() }, "Bearer test-token", canceled.Token));
    }

    private sealed class ResponseHandler(int code, string body) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            return Task.FromResult(new HttpResponseMessage((HttpStatusCode)code) { Content = new StringContent(body) });
        }
    }
}
