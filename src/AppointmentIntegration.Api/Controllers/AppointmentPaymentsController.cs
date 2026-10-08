using System.Security.Claims;
using AppointmentIntegration.Api.DTOs.AppointmentPayment;
using AppointmentIntegration.Api.Services.Interfaces;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AppointmentIntegration.Api.Controllers;

[ApiController]
[Route("api/appointments/{appointmentId:int}/payment")]
[Authorize]
public class AppointmentPaymentsController : ControllerBase
{
    private readonly IAppointmentPaymentService _paymentService;

    public AppointmentPaymentsController(
        IAppointmentPaymentService paymentService)
    {
        _paymentService = paymentService;
    }

    [HttpGet]
    public async Task<IActionResult> GetPayment(
        int appointmentId,
        CancellationToken cancellationToken)
    {
        if (!TryGetPatientId(out var patientId))
        {
            return Unauthorized(new
            {
                message = "A valid patient identity is required."
            });
        }

        var payment =
            await _paymentService.GetPaymentAsync(
                patientId,
                appointmentId,
                cancellationToken);

        if (payment is null)
        {
            return NotFound(new
            {
                message =
                    "Payment information was not found for this appointment."
            });
        }

        return Ok(payment);
    }

    [HttpPost("method")]
    public async Task<IActionResult> SelectPaymentMethod(
        int appointmentId,
        [FromBody] SelectAppointmentPaymentMethodDto request,
        CancellationToken cancellationToken)
    {
        if (!TryGetPatientId(out var patientId))
        {
            return Unauthorized(new
            {
                message = "A valid patient identity is required."
            });
        }

        try
        {
            var payment =
                await _paymentService.SelectPaymentMethodAsync(
                    patientId,
                    appointmentId,
                    request,
                    cancellationToken);

            return Ok(payment);
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
        catch
        {
            return StatusCode(
                StatusCodes.Status500InternalServerError,
                new
                {
                    message =
                        "Payment could not be processed. Please try again."
                });
        }
    }

    [HttpPost("receipt")]
    [Consumes("multipart/form-data")]
    public async Task<IActionResult> UploadReceipt(
        int appointmentId,
        [FromForm] AppointmentReceiptUploadDto request,
        CancellationToken cancellationToken)
    {
        if (!TryGetPatientId(out var patientId))
        {
            return Unauthorized(new
            {
                message = "A valid patient identity is required."
            });
        }

        if (request.Receipt is null)
        {
            return BadRequest(new
            {
                message =
                    "Please select a bank transfer receipt."
            });
        }

        try
        {
            var payment =
                await _paymentService.UploadReceiptAsync(
                    patientId,
                    appointmentId,
                    request.Receipt,
                    cancellationToken);

            return Ok(payment);
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
        catch
        {
            return StatusCode(
                StatusCodes.Status500InternalServerError,
                new
                {
                    message =
                        "Receipt upload failed. Please try again."
                });
        }
    }

    private bool TryGetPatientId(
        out Guid patientId)
    {
        patientId = Guid.Empty;

        var value =
            User.FindFirstValue(
                ClaimTypes.NameIdentifier);

        return Guid.TryParse(
            value,
            out patientId);
    }
}