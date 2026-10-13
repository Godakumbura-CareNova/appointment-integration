using System.Security.Claims;
using AppointmentIntegration.Api.DTOs.Appointment;
using AppointmentIntegration.Api.Exceptions;
using AppointmentIntegration.Api.Services.Interfaces;
using FluentValidation;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AppointmentIntegration.Api.Controllers;

[ApiController]
[Route("api/appointments")]
[Authorize]
public class AppointmentsController : ControllerBase
{
    private readonly IAppointmentBookingService _bookingService;
    private readonly IValidator<BookAppointmentRequestDto> _validator;

    public AppointmentsController(
        IAppointmentBookingService bookingService,
        IValidator<BookAppointmentRequestDto> validator)
    {
        _bookingService = bookingService;
        _validator = validator;
    }

    [HttpPost]
    public async Task<ActionResult<AppointmentResponseDto>> Book(
        [FromBody] BookAppointmentRequestDto request,
        CancellationToken cancellationToken)
    {
        var validation = await _validator.ValidateAsync(request, cancellationToken);

        if (!validation.IsValid)
        {
            return BadRequest(new
            {
                message = "Please select a doctor and appointment slot.",
                errors = validation.ToDictionary()
            });
        }

        if (!Guid.TryParse(
                User.FindFirstValue(ClaimTypes.NameIdentifier),
                out var patientId) ||
            patientId == Guid.Empty)
        {
            return Unauthorized(new
            {
                message = "The token does not identify a valid patient."
            });
        }

        try
        {
            var appointment = await _bookingService.BookAsync(
                patientId,
                request,
                cancellationToken);

            return StatusCode(
                StatusCodes.Status201Created,
                appointment);
        }
        catch (DuplicateBookingException exception)
        {
            return Conflict(new
            {
                message = exception.Message
            });
        }
        catch (SlotUnavailableException exception)
        {
            return Conflict(new
            {
                message = exception.Message
            });
        }
        catch (ArgumentException exception)
        {
            return BadRequest(new
            {
                message = exception.Message
            });
        }
        catch
        {
            return StatusCode(
                StatusCodes.Status500InternalServerError,
                new
                {
                    message = "Appointment creation failed. Please try again."
                });
        }
    }
}