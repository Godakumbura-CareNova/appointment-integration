using AppointmentIntegration.Api.DTOs.PublicContent;
using AppointmentIntegration.Api.Services;
using AppointmentIntegration.Api.Validators;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
namespace AppointmentIntegration.Api.Controllers;
[ApiController]
public sealed class ContactInquiriesController(ContactInquiryService service, ContactInquiryValidator validator) : ControllerBase
{
    [AllowAnonymous, HttpPost("api/public/contact-inquiries"), EnableRateLimiting("Inquiries"), RequestSizeLimit(32_000)]
    public async Task<IActionResult> Submit(ContactInquiryRequestDto request, CancellationToken token)
    {
        var validation = await validator.ValidateAsync(request, token);
        if (!validation.IsValid) return BadRequest(new { message = "Please check your inquiry details.", errors = validation.ToDictionary() });
        var saved = await service.SubmitAsync(request, token);
        return StatusCode(StatusCodes.Status201Created, new { saved.Id, saved.SubmittedAtUtc, message = "Your inquiry has been received. Thank you for contacting CareNova." });
    }
    [Authorize(Policy = "Admin"), HttpGet("api/admin/contact-inquiries")]
    public async Task<IActionResult> List([FromQuery] int page = 1, [FromQuery] int pageSize = 20, CancellationToken token = default)
    {
        if (page is < 1 or > 100000 || pageSize is < 1 or > 100) return BadRequest(new { message = "Please use valid pagination." });
        return Ok(await service.ListAsync(page, pageSize, token));
    }
    [Authorize(Policy = "Admin"), HttpPatch("api/admin/contact-inquiries/{id:guid}/reviewed")]
    public async Task<IActionResult> Review(Guid id, CancellationToken token)
    {
        var inquiry = await service.ReviewAsync(id, token);
        return inquiry is null ? NotFound(new { message = "This inquiry is unavailable." }) : Ok(inquiry);
    }
}
