namespace AppointmentIntegration.Api.Models;
public sealed class PharmacyInformation
{
    public int Id { get; set; } = 1;
    public string ContentJson { get; set; } = "";
    public Guid Revision { get; set; }
    public DateTime UpdatedAtUtc { get; set; }
}
