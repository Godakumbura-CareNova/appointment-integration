using AppointmentIntegration.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
namespace AppointmentIntegration.Api.Controllers;
[ApiController, AllowAnonymous, Route("api/public")]
public class PublicContentController(PublicContentService content, ILogger<PublicContentController> logger) : ControllerBase
{
    [HttpGet("home")]
    public async Task<IActionResult> Home(CancellationToken token)
    {
        try { return Ok(await content.GetHomeAsync(token)); }
        catch (Exception e) when (e is not OperationCanceledException)
        {
            logger.LogError(e, "Public home information could not be loaded");
            return StatusCode(503, new { message = "Home page information is unavailable. Please retry." });
        }
    }
}
