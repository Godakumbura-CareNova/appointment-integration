using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.Options;
namespace AppointmentIntegration.Api.Services;
public sealed class PublicContentOptions
{
    public string Introduction { get; set; } = "CareNova connects you with pharmacy services and healthcare professionals. Explore our medicine catalogue, discover doctors and register to access patient services.";
    public List<ServiceContent> Services { get; set; } = [];
    public List<NoticeContent> Notices { get; set; } = [];
    public List<int> FeaturedMedicineIds { get; set; } = [];
    public List<Guid> FeaturedDoctorIds { get; set; } = [];
    public string PharmacyBaseUrl { get; set; } = "http://localhost:5134/";
    public string DoctorBaseUrl { get; set; } = "http://localhost:5135/";
}
public record ServiceContent(string Title, string Description);
public record NoticeContent(string Title, string Message);
public sealed class HomePageResponse
{
    public string Introduction { get; set; } = "";
    public List<ServiceContent> Services { get; set; } = [];
    public List<NoticeContent> Notices { get; set; } = [];
    public List<JsonElement> FeaturedMedicines { get; set; } = [];
    public List<JsonElement> FeaturedDoctors { get; set; } = [];
    public List<string> SectionErrors { get; set; } = [];
}
public class PublicContentService(IHttpClientFactory clients, IOptions<PublicContentOptions> options, ILogger<PublicContentService> logger, Interfaces.IPharmacyInformationReader information)
{
    public async Task<HomePageResponse> GetHomeAsync(CancellationToken token)
    {
        var settings = options.Value;
        var medicines = LoadAsync(settings.PharmacyBaseUrl, "medicines", settings.FeaturedMedicineIds.Select(id => id.ToString()).ToArray(), token);
        var doctors = LoadAsync(settings.DoctorBaseUrl, "doctors", settings.FeaturedDoctorIds.Select(id => id.ToString()).ToArray(), token);
        await Task.WhenAll(medicines, doctors);
        var home = new HomePageResponse { Introduction = settings.Introduction, Services = settings.Services, Notices = settings.Notices, FeaturedMedicines = medicines.Result.Items, FeaturedDoctors = doctors.Result.Items };
        using var lookupBudget = CancellationTokenSource.CreateLinkedTokenSource(token);
        lookupBudget.CancelAfter(TimeSpan.FromSeconds(2));
        try {
            var saved = await information.GetAsync(lookupBudget.Token).WaitAsync(lookupBudget.Token);
            home.Introduction = saved.Introduction;
            home.Services = saved.Services;
        }
        catch (OperationCanceledException) when (!token.IsCancellationRequested) {
            logger.LogWarning("Using configured home information after the optional pharmacy information lookup timed out");
        }
        catch (Exception exception) when (exception is not OperationCanceledException) {
            logger.LogWarning(exception, "Using configured home information while pharmacy information storage is unavailable");
        }
        if (medicines.Result.Failed) home.SectionErrors.Add("Featured medicines are temporarily unavailable.");
        if (doctors.Result.Failed) home.SectionErrors.Add("Featured doctors are temporarily unavailable.");
        return home;
    }
    private async Task<(List<JsonElement> Items, bool Failed)> LoadAsync(string baseUrl, string kind, string[] ids, CancellationToken token)
    {
        var items = new List<JsonElement>(); var failed = false;
        try
        {
            var client = clients.CreateClient("PublicContent");
            var root = new Uri(baseUrl.TrimEnd('/') + "/");
            if (ids.Length == 0)
            {
                using var result = await client.GetFromJsonAsync<JsonDocument>(new Uri(root, $"api/public/{kind}?pageSize=4"), token);
                if (result is null || !result.RootElement.TryGetProperty("items", out var list) || list.ValueKind != JsonValueKind.Array) throw new JsonException("Missing public items.");
                items.AddRange(list.EnumerateArray().Take(4).Select(item => item.Clone()));
            }
            else
            {
                var selected = await Task.WhenAll(ids.Take(4).Select(id => LoadSelectedAsync(client, root, kind, id, token)));
                items.AddRange(selected.Where(result => result.Item.HasValue).Select(result => result.Item!.Value));
                failed = selected.Any(result => result.Failed);
            }
        }
        catch (Exception e) when (e is HttpRequestException or JsonException or TaskCanceledException or UriFormatException)
        {
            token.ThrowIfCancellationRequested();
            logger.LogWarning(e, "Public {Section} information is unavailable", kind); failed = true;
        }
        return (items, failed);
    }
    private async Task<(JsonElement? Item, bool Failed)> LoadSelectedAsync(HttpClient client, Uri root, string kind, string id, CancellationToken token)
    {
        try
        {
            using var response = await client.GetAsync(new Uri(root, $"api/public/{kind}/{Uri.EscapeDataString(id)}"), token);
            if (response.StatusCode == System.Net.HttpStatusCode.NotFound) return (null, false);
            response.EnsureSuccessStatusCode();
            using var value = await response.Content.ReadFromJsonAsync<JsonDocument>(cancellationToken: token);
            return (value?.RootElement.Clone(), value is null);
        }
        catch (Exception e) when (e is HttpRequestException or JsonException or TaskCanceledException)
        {
            token.ThrowIfCancellationRequested();
            logger.LogWarning(e, "Featured {Section} item is unavailable", kind);
            return (null, true);
        }
    }
}
