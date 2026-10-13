using AppointmentIntegration.Api.DTOs.PublicContent;
namespace AppointmentIntegration.Api.Services.Interfaces;
public interface IPharmacyInformationReader
{
    Task<PharmacyInformationDto> GetAsync(CancellationToken token);
}
