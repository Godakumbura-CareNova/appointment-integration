using AppointmentIntegration.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
namespace AppointmentIntegration.Api.Controllers;
[ApiController, Authorize(Policy = "Admin")]
public sealed class PharmacyImagesController(PharmacyImageService service) : ControllerBase
{
    [HttpPost("api/admin/pharmacy-information/images"), RequestSizeLimit(PharmacyImageService.MaxBytes + 65536)]
    public async Task<IActionResult> Upload(IFormFile file, CancellationToken token)
    {
        try { return Ok(new { url = await service.UploadAsync(file, token) }); }
        catch (ArgumentException exception) { return BadRequest(new { message = exception.Message }); }
    }
}
