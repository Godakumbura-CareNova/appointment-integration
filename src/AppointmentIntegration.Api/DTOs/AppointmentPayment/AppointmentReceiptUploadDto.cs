using Microsoft.AspNetCore.Http;

namespace AppointmentIntegration.Api.DTOs.AppointmentPayment;

public class AppointmentReceiptUploadDto
{
    public IFormFile? Receipt { get; set; }
}