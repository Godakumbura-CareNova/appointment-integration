using System.Security.Claims;
using AppointmentIntegration.Api.DTOs.Cancellation;
using AppointmentIntegration.Api.Services.Interfaces;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace AppointmentIntegration.Api.Controllers;

[ApiController]
[Route("api/patient/appointments/{appointmentId:int:min(1)}/cancellation")]
[Authorize(Roles = "Patient,User")]
public sealed class AppointmentCancellationsController(IAppointmentCancellationService service, ILogger<AppointmentCancellationsController> logger) : ControllerBase
{
    [HttpGet] public Task<IActionResult> Eligibility(int appointmentId, CancellationToken ct) => Execute(appointmentId, null, ct);
    [HttpPost] public Task<IActionResult> Cancel(int appointmentId, CancelAppointmentRequestDto request, CancellationToken ct) => Execute(appointmentId, request, ct);
    private async Task<IActionResult> Execute(int id, CancelAppointmentRequestDto? request, CancellationToken ct)
    {
        if (!Guid.TryParse(User.FindFirstValue(ClaimTypes.NameIdentifier), out var patientId) || patientId == Guid.Empty) return Unauthorized(new { message = "A valid patient identity is required." });
        try
        {
            if (request is not null) return Ok(await service.CancelAsync(patientId, id, request, ct));
            var eligibility = await service.GetEligibilityAsync(patientId, id, ct);
            return eligibility is null ? NotFound(new { message = "Appointment not found." }) : Ok(eligibility);
        }
        catch (KeyNotFoundException) { return NotFound(new { message = "Appointment not found." }); }
        catch (ArgumentException ex) { return BadRequest(new { message = ex.Message }); }
        catch (DbUpdateConcurrencyException) { return Conflict(new { message = "Appointment or payment information changed. Refresh and confirm again." }); }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
        catch (Exception ex) { logger.LogError(ex, "Appointment cancellation failed."); return StatusCode(500, new { message = "Could not process cancellation. Refresh to check its status and try again." }); }
    }
}
