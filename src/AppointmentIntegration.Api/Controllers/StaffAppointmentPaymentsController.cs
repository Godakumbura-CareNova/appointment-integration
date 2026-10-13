using System.Security.Claims;
using AppointmentIntegration.Api.DTOs.AppointmentPayment;
using AppointmentIntegration.Api.Repositories;
using AppointmentIntegration.Api.Security;
using AppointmentIntegration.Api.Services.Interfaces;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AppointmentIntegration.Api.Controllers;

[ApiController]
[Route("api/staff/appointment-payments")]
[Authorize(Policy = AuthorizationPolicies.PharmacyStaff)]
public class StaffAppointmentPaymentsController : ControllerBase
{
    private readonly IAppointmentPaymentRepository _repository;
    private readonly IAppointmentPaymentService _paymentService;
    private readonly IBlobStorageService _blobStorageService;

    public StaffAppointmentPaymentsController(
        IAppointmentPaymentRepository repository,
        IAppointmentPaymentService paymentService,
        IBlobStorageService blobStorageService)
    {
        _repository = repository;
        _paymentService = paymentService;
        _blobStorageService = blobStorageService;
    }

    [HttpGet("receipts")]
    public async Task<IActionResult> GetPendingReceipts(
        CancellationToken cancellationToken)
    {
        var receipts =
            await _repository.GetPendingReceiptsAsync(
                cancellationToken);

        var result =
            receipts.Select(receipt => new
            {
                receipt.Id,
                receipt.AppointmentId,
                AppointmentReference =
                    receipt.AppointmentPayment?
                        .Appointment?
                        .AppointmentReference
                    ?? string.Empty,

                receipt.PatientId,

                Amount =
                    receipt.AppointmentPayment?.Amount
                    ?? 0m,

                FileName =
                    receipt.OriginalFileName,

                receipt.ContentType,
                receipt.SizeBytes,

                Status =
                    receipt.Status.ToString(),

                receipt.UploadedAtUtc
            });

        return Ok(result);
    }

    [HttpGet("receipts/{receiptId:int}/file")]
    public async Task<IActionResult> GetReceiptFile(
        int receiptId,
        CancellationToken cancellationToken)
    {
        var receipt =
            await _repository.GetReceiptByIdAsync(
                receiptId,
                cancellationToken);

        if (receipt is null)
        {
            return NotFound(new
            {
                message = "Receipt was not found."
            });
        }

        try
        {
            var file =
                await _blobStorageService.DownloadReceiptAsync(
                    receipt.BlobName,
                    cancellationToken);

            return File(
                file.Content,
                file.ContentType,
                receipt.OriginalFileName,
                enableRangeProcessing: true);
        }
        catch (InvalidOperationException ex)
        {
            return StatusCode(
                StatusCodes.Status503ServiceUnavailable,
                new
                {
                    message = ex.Message
                });
        }
    }

    [HttpPost("appointments/{appointmentId:int}/receipt/verify")]
    public async Task<IActionResult> VerifyReceipt(
        int appointmentId,
        [FromBody] AppointmentReceiptVerificationDto request,
        CancellationToken cancellationToken)
    {
        if (!TryGetUserId(out var staffId))
        {
            return Unauthorized(new
            {
                message = "A valid staff identity is required."
            });
        }

        try
        {
            var result =
                await _paymentService.VerifyReceiptAsync(
                    staffId,
                    appointmentId,
                    request,
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
    }

    private bool TryGetUserId(
        out Guid userId)
    {
        userId = Guid.Empty;

        var value =
            User.FindFirstValue(
                ClaimTypes.NameIdentifier);

        return Guid.TryParse(
            value,
            out userId);
    }
}