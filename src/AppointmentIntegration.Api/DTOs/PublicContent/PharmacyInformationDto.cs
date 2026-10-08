using AppointmentIntegration.Api.Services;
namespace AppointmentIntegration.Api.DTOs.PublicContent;

public sealed class PharmacyInformationDto
{
    public string Introduction { get; set; } = "";
    public string Background { get; set; } = "";
    public string Mission { get; set; } = "";
    public string Vision { get; set; } = "";
    public List<ServiceContent> Services { get; set; } = [];
    public List<OpeningHoursDto> OpeningHours { get; set; } = [];
    public string Address { get; set; } = "";
    public string Phone { get; set; } = "";
    public string Email { get; set; } = "";
    public string LocationDescription { get; set; } = "";
    public string MapEmbedUrl { get; set; } = "";
    public List<PharmacyImageDto> Images { get; set; } = [];
    public Guid Revision { get; set; }
}
public record OpeningHoursDto(string Day, string Hours);
public record PharmacyImageDto(string Url, string Caption);
