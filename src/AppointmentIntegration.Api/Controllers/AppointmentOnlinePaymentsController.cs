using System.Security.Claims;
using AppointmentIntegration.Api.DTOs.AppointmentPayment;
using AppointmentIntegration.Api.Exceptions;
using AppointmentIntegration.Api.Services.Interfaces;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Net.Http.Headers;

namespace AppointmentIntegration.Api.Controllers;

[ApiController]
[Route("api/appointments/{appointmentId:int}/payment/online")]
[Authorize]
public class AppointmentOnlinePaymentsController : ControllerBase
{
    private readonly IAppointmentOnlinePaymentService _service;

    public AppointmentOnlinePaymentsController(
        IAppointmentOnlinePaymentService service)
    {
        _service = service;
    }

    [HttpPost("start")]
    public async Task<IActionResult> Start(
        int appointmentId,
        [FromBody] StartAppointmentOnlinePaymentDto request,
        CancellationToken cancellationToken)
    {
        if (!TryGetUserId(out var patientId))
        {
            return Unauthorized(new
            {
                message = "Please sign in again."
            });
        }

        try
        {
            var result =
                await _service.StartAsync(
                    patientId,
                    appointmentId,
                    request,
                    Request.Headers[HeaderNames.Origin]
                        .FirstOrDefault(),
                    cancellationToken);

            return Ok(result);
        }
        catch (ArgumentException ex)
        {
            return BadRequest(new
            {
                message = ex.Message
            });
        }
        catch (KeyNotFoundException ex)
        {
            return NotFound(new
            {
                message = ex.Message
            });
        }
        catch (InvalidOperationException ex)
        {
            return Conflict(new
            {
                message = ex.Message
            });
        }
        catch (PaymentGatewayUnavailableException ex)
        {
            return StatusCode(
                StatusCodes.Status503ServiceUnavailable,
                new
                {
                    message = ex.Message,
                    retryable = true
                });
        }
    }

    [HttpGet("{attemptId:int}")]
    public async Task<IActionResult> GetResult(
        int appointmentId,
        int attemptId,
        CancellationToken cancellationToken)
    {
        if (!TryGetUserId(out var patientId))
        {
            return Unauthorized();
        }

        try
        {
            return Ok(
                await _service.GetResultAsync(
                    patientId,
                    appointmentId,
                    attemptId,
                    cancellationToken));
        }
        catch (KeyNotFoundException ex)
        {
            return NotFound(new
            {
                message = ex.Message
            });
        }
    }

    [HttpPost("{attemptId:int}/cancel")]
    public async Task<IActionResult> Cancel(
        int appointmentId,
        int attemptId,
        CancellationToken cancellationToken)
    {
        if (!TryGetUserId(out var patientId))
        {
            return Unauthorized();
        }

        try
        {
            return Ok(
                await _service.CancelAsync(
                    patientId,
                    appointmentId,
                    attemptId,
                    cancellationToken));
        }
        catch (KeyNotFoundException ex)
        {
            return NotFound(new
            {
                message = ex.Message
            });
        }
    }

    private bool TryGetUserId(
        out Guid userId)
    {
        userId = Guid.Empty;

        return Guid.TryParse(
            User.FindFirstValue(
                ClaimTypes.NameIdentifier),
            out userId);
    }
}


[ApiController]
[Route("api/appointment-payments/payhere/notify")]
[AllowAnonymous]
public class AppointmentPayHereNotifyController : ControllerBase
{
    private readonly IAppointmentOnlinePaymentService _service;
    private readonly ILogger<AppointmentPayHereNotifyController> _logger;

    public AppointmentPayHereNotifyController(
        IAppointmentOnlinePaymentService service,
        ILogger<AppointmentPayHereNotifyController> logger)
    {
        _service = service;
        _logger = logger;
    }

    [HttpPost]
    [Consumes(
        "application/x-www-form-urlencoded",
        "multipart/form-data")]
    [RequestSizeLimit(64 * 1024)]
    public async Task<IActionResult> Receive(
        CancellationToken cancellationToken)
    {
        var form =
            await Request.ReadFormAsync(
                cancellationToken);

        var fields =
            form.ToDictionary(
                x => x.Key,
                x => x.Value.ToString(),
                StringComparer.Ordinal);

        try
        {
            await _service.HandleNotificationAsync(
                fields,
                cancellationToken);

            return Ok();
        }
        catch (InvalidWebhookSignatureException ex)
        {
            _logger.LogWarning(
                "PayHere callback rejected: {Reason}",
                ex.Message);

            return BadRequest();
        }
    }
}