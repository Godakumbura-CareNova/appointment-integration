using System.Security.Claims;
using AppointmentIntegration.Api.Security;
using AppointmentIntegration.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AppointmentIntegration.Api.Controllers;

[ApiController]
public sealed class AppointmentDashboardController(AppointmentDashboardService service) : ControllerBase
{
    [Authorize(Roles = "Patient,User")]
    [HttpGet("api/patient/dashboard/appointments")]
    public async Task<IActionResult> Patient(CancellationToken ct)
    {
        if (!Guid.TryParse(User.FindFirstValue(ClaimTypes.NameIdentifier), out var id) || id == Guid.Empty) return Unauthorized();
        return Ok(await service.GetPatientAsync(id, ct));
    }

    [Authorize(Policy = AuthorizationPolicies.PharmacyStaff)]
    [HttpGet("api/staff/dashboard/appointment-payments")]
    public async Task<IActionResult> Staff(CancellationToken ct) => Ok(await service.GetStaffPaymentsAsync(ct));
}
