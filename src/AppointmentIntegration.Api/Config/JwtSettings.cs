namespace AppointmentIntegration.Api.Config;
public sealed class JwtSettings
{
    public string Secret { get; set; } = "";
    public string Issuer { get; set; } = "CareNova.UserAuth";
    public string Audience { get; set; } = "CareNova.Client";
}
