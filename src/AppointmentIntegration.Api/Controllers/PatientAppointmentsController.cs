using System.Security.Claims;
using AppointmentIntegration.Api.Services.Interfaces;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AppointmentIntegration.Api.Controllers;

[ApiController]
[Route("api/appointments")]
[Authorize(Roles = "Patient,User")]
public sealed class PatientAppointmentsController(IPatientAppointmentService service, ILogger<PatientAppointmentsController> logger) : ControllerBase
{
    [HttpGet]
    public Task<IActionResult> List(CancellationToken cancellationToken) => Read(null, cancellationToken);

    [HttpGet("{appointmentId:int:min(1)}")]
    public Task<IActionResult> Detail(int appointmentId, CancellationToken cancellationToken) => Read(appointmentId, cancellationToken);

    private async Task<IActionResult> Read(int? appointmentId, CancellationToken cancellationToken)
    {
        if (!Guid.TryParse(User.FindFirstValue(ClaimTypes.NameIdentifier), out var patientId) || patientId == Guid.Empty)
            return Unauthorized(new { message = "The token does not identify a valid patient." });
        try
        {
            if (appointmentId is null) return Ok(await service.GetAppointmentsAsync(patientId, cancellationToken));
            var appointment = await service.GetAppointmentAsync(patientId, appointmentId.Value, cancellationToken);
            return appointment is null ? NotFound(new { message = "Appointment not found." }) : Ok(appointment);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
        catch (Exception exception)
        {
            logger.LogError(exception, "Could not retrieve patient appointments.");
            return StatusCode(500, new { message = "Could not load appointment information. Please try again." });
        }
    }
}
