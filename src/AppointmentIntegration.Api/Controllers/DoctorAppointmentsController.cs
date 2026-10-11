using System.Security.Claims;
using AppointmentIntegration.Api.DTOs.Appointment;
using AppointmentIntegration.Api.Exceptions;
using AppointmentIntegration.Api.Services.Interfaces;
using AppointmentIntegration.Api.Validators;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace AppointmentIntegration.Api.Controllers;

[ApiController]
[Route("api/doctor/appointments")]
[Authorize(Roles = "Doctor")]
public sealed class DoctorAppointmentsController(IDoctorAppointmentService service, ILogger<DoctorAppointmentsController> logger) : ControllerBase
{
    private bool Identity(out Guid id) => Guid.TryParse(User.FindFirstValue(ClaimTypes.NameIdentifier) ?? User.FindFirstValue("sub"), out id) && id != Guid.Empty;

    [HttpGet]
    public Task<IActionResult> List(CancellationToken ct) => Execute(async id => Ok(await service.GetAppointmentsAsync(id, ct)));

    [HttpGet("{appointmentId:int:min(1)}")]
    public Task<IActionResult> Detail(int appointmentId, CancellationToken ct) => Execute(async id => {
        var row = await service.GetAppointmentAsync(id, appointmentId, ct); return row is null ? NotFound() : Ok(row);
    });

    [HttpPost("patient-access")]
    public Task<IActionResult> PatientAccess(PatientAccessRequestDto request, CancellationToken ct) => Execute(async id => {
        if (!request.IsValid) return BadRequest(new { message = "Supply 1 to 100 unique, valid patient IDs." });
        return Ok(new { patientIds = await service.GetAssignedPatientIdsAsync(id, request.PatientIds!, ct) });
    });

    [HttpPatch("{appointmentId:int:min(1)}/status")]
    public Task<IActionResult> Update(int appointmentId, UpdateAppointmentStatusDto request, CancellationToken ct) => Execute(async id => {
        var validation = await new UpdateAppointmentStatusValidator().ValidateAsync(request, ct);
        if (!validation.IsValid) return BadRequest(new { message = validation.Errors[0].ErrorMessage });
        var result = await service.UpdateStatusAsync(id, appointmentId, request, ct); return result is null ? NotFound() : Ok(result);
    });

    private async Task<IActionResult> Execute(Func<Guid, Task<IActionResult>> action)
    {
        if (!Identity(out var id)) return Unauthorized();
        try { return await action(id); }
        catch (InvalidAppointmentStatusTransitionException ex) { return BadRequest(new { message = ex.Message }); }
        catch (DbUpdateConcurrencyException) { return Conflict(new { message = "This appointment changed. Refresh it before trying again." }); }
        catch (OperationCanceledException) when (HttpContext.RequestAborted.IsCancellationRequested) { throw; }
        catch (Exception ex) { logger.LogError(ex, "Doctor appointment request failed"); return StatusCode(500, new { message = "Could not process the appointment. Please try again." }); }
    }
}
