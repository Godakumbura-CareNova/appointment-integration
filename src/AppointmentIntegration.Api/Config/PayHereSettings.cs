namespace AppointmentIntegration.Api.Config;

public class PayHereSettings
{
    public string MerchantId { get; set; } = string.Empty;

    public string MerchantSecret { get; set; } = string.Empty;

    public bool Sandbox { get; set; } = true;

    public bool AllowLivePayments { get; set; }

    public string NotifyUrl { get; set; } = string.Empty;

    public string FrontendBaseUrl { get; set; } = string.Empty;

    public string Currency { get; set; } = "LKR";

    public int MaxAttempts { get; set; } = 5;

    public bool IsConfigured =>
        !string.IsNullOrWhiteSpace(MerchantId)
        &&
        !string.IsNullOrWhiteSpace(MerchantSecret)
        &&
        Uri.TryCreate(
            NotifyUrl,
            UriKind.Absolute,
            out var notify)
        &&
        (notify.Scheme == Uri.UriSchemeHttps ||
         notify.Scheme == Uri.UriSchemeHttp)
        &&
        (Sandbox || AllowLivePayments);
}