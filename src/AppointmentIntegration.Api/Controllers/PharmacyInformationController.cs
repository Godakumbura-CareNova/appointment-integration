using AppointmentIntegration.Api.DTOs.PublicContent;
using AppointmentIntegration.Api.Services;
using AppointmentIntegration.Api.Validators;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
namespace AppointmentIntegration.Api.Controllers;

[ApiController]
public sealed class PharmacyInformationController(PharmacyInformationService service, PharmacyInformationValidator validator) : ControllerBase
{
    [AllowAnonymous, HttpGet("api/public/pharmacy-information")]
    public async Task<IActionResult> PublicInformation(CancellationToken token) => Ok(await service.GetAsync(token));
    [Authorize(Policy = "Admin"), HttpGet("api/admin/pharmacy-information")]
    public async Task<IActionResult> AdminInformation(CancellationToken token) => Ok(await service.GetAsync(token));
    [Authorize(Policy = "Admin"), HttpPut("api/admin/pharmacy-information"), RequestSizeLimit(100_000)]
    public async Task<IActionResult> Save(PharmacyInformationDto content, CancellationToken token)
    {
        var validation = await validator.ValidateAsync(content, token);
        if (!validation.IsValid) return BadRequest(new { message = "Please check the pharmacy information.", errors = validation.ToDictionary() });
        try { return Ok(await service.SaveAsync(content, token)); }
        catch (InformationConflictException) { return Conflict(new { message = "The pharmacy information changed since you opened it. Reload before saving again." }); }
        catch (ArgumentException exception) { return BadRequest(new { message = exception.Message }); }
    }
}
