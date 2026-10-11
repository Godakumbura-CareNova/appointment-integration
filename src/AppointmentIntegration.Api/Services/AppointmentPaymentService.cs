using AppointmentIntegration.Api.Clients;
using AppointmentIntegration.Api.DTOs.AppointmentPayment;
using AppointmentIntegration.Api.Models;
using AppointmentIntegration.Api.Repositories;
using AppointmentIntegration.Api.Services.Interfaces;
using Microsoft.AspNetCore.Http;
using Microsoft.EntityFrameworkCore;

namespace AppointmentIntegration.Api.Services;

public class AppointmentPaymentService : IAppointmentPaymentService
{
    private readonly IAppointmentPaymentRepository _repository;
    private readonly DoctorPaymentClient _doctorPaymentClient;
    private readonly IBlobStorageService _blobStorageService;
    private readonly TimeProvider _timeProvider;

    public AppointmentPaymentService(
        IAppointmentPaymentRepository repository,
        DoctorPaymentClient doctorPaymentClient,
        IBlobStorageService blobStorageService,
        TimeProvider timeProvider)
    {
        _repository = repository;
        _doctorPaymentClient = doctorPaymentClient;
        _blobStorageService = blobStorageService;
        _timeProvider = timeProvider;
    }

    public async Task<AppointmentPaymentResponseDto> SelectPaymentMethodAsync(
        Guid patientId,
        int appointmentId,
        SelectAppointmentPaymentMethodDto request,
        CancellationToken cancellationToken = default)
    {
        if (patientId == Guid.Empty)
        {
            throw new ArgumentException(
                "A valid patient identity is required.");
        }

        if (appointmentId <= 0)
        {
            throw new ArgumentException(
                "A valid appointment is required.");
        }

        if (!TryParseMethod(request.Method, out var method))
        {
            throw new ArgumentException(
                "Select a valid payment method: Cash, BankTransfer, or PaymentGateway.");
        }

        var appointment =
            await _repository.GetAppointmentAsync(
                patientId,
                appointmentId,
                cancellationToken);

        if (appointment is null)
        {
            throw new KeyNotFoundException(
                "The appointment could not be found.");
        }

        var doctor =
            await _doctorPaymentClient.GetDoctorAsync(
                appointment.DoctorId,
                cancellationToken);

        if (doctor is null)
        {
            throw new InvalidOperationException(
                "The doctor information could not be loaded.");
        }

        if (doctor.ConsultationFee is null ||
            doctor.ConsultationFee <= 0)
        {
            throw new InvalidOperationException(
                "A valid consultation fee has not been configured for this doctor.");
        }

        var payment =
            await _repository.GetByAppointmentAsync(
                patientId,
                appointmentId,
                cancellationToken);

        if (payment?.Status ==
            AppointmentPaymentStatus.Successful)
        {
            throw new InvalidOperationException(
                "This appointment has already been paid.");
        }

        if (payment?.Status ==
            AppointmentPaymentStatus.ReceiptUnderVerification)
        {
            throw new InvalidOperationException(
                "The bank transfer receipt is currently being verified. The payment method cannot be changed.");
        }

        var now =
            _timeProvider.GetUtcNow().UtcDateTime;

        if (payment is null)
        {
            payment = new AppointmentPayment
            {
                AppointmentId = appointment.Id,
                PatientId = patientId,
                CreatedAtUtc = now
            };

            _repository.Add(payment);
        }

        payment.Amount = doctor.ConsultationFee.Value;
        payment.Method = method;

        payment.Status = method switch
        {
            AppointmentPaymentMethod.Cash =>
                AppointmentPaymentStatus.Pending,

            AppointmentPaymentMethod.BankTransfer =>
                AppointmentPaymentStatus.AwaitingBankTransferReceipt,

            AppointmentPaymentMethod.PaymentGateway =>
                AppointmentPaymentStatus.AwaitingGatewayPayment,

            _ => AppointmentPaymentStatus.Pending
        };

        payment.UpdatedAtUtc = now;

        try
        {
            await _repository.SaveChangesAsync(
                cancellationToken);
        }
        catch (DbUpdateException)
        {
            throw new InvalidOperationException(
                "The payment was updated by another request. Refresh and try again.");
        }

        return ToResponse(payment, appointment);
    }

    public async Task<AppointmentPaymentResponseDto?> GetPaymentAsync(
        Guid patientId,
        int appointmentId,
        CancellationToken cancellationToken = default)
    {
        var payment =
            await _repository.GetByAppointmentAsync(
                patientId,
                appointmentId,
                cancellationToken);

        if (payment is null ||
            payment.Appointment is null)
        {
            return null;
        }

        return ToResponse(
            payment,
            payment.Appointment);
    }

    public async Task<AppointmentPaymentResponseDto> UploadReceiptAsync(
        Guid patientId,
        int appointmentId,
        IFormFile receipt,
        CancellationToken cancellationToken = default)
    {
        if (patientId == Guid.Empty)
        {
            throw new ArgumentException(
                "A valid patient identity is required.");
        }

        if (appointmentId <= 0)
        {
            throw new ArgumentException(
                "A valid appointment is required.");
        }

        if (receipt is null || receipt.Length == 0)
        {
            throw new ArgumentException(
                "Please select a bank transfer receipt.");
        }

        const long maxSize = 5 * 1024 * 1024;

        if (receipt.Length > maxSize)
        {
            throw new ArgumentException(
                "Receipt file size cannot exceed 5 MB.");
        }

        var allowedContentTypes = new[]
        {
            "image/jpeg",
            "image/png",
            "application/pdf"
        };

        if (!allowedContentTypes.Contains(
                receipt.ContentType,
                StringComparer.OrdinalIgnoreCase))
        {
            throw new ArgumentException(
                "Only JPG, PNG, or PDF receipts are allowed.");
        }

        var payment =
            await _repository.GetByAppointmentAsync(
                patientId,
                appointmentId,
                cancellationToken);

        if (payment is null ||
            payment.Appointment is null)
        {
            throw new KeyNotFoundException(
                "Payment information was not found for this appointment.");
        }

        if (payment.Method !=
            AppointmentPaymentMethod.BankTransfer)
        {
            throw new InvalidOperationException(
                "Bank transfer is not the selected payment method.");
        }

        if (payment.Status ==
            AppointmentPaymentStatus.Successful)
        {
            throw new InvalidOperationException(
                "This appointment payment has already been completed.");
        }

        if (payment.Status ==
            AppointmentPaymentStatus.ReceiptUnderVerification)
        {
            throw new InvalidOperationException(
                "A receipt is already being verified.");
        }

        BlobUploadResult? uploadedBlob = null;

        await ValidateReceiptContentAsync(receipt, cancellationToken);

        try
        {
            await using var stream =
                receipt.OpenReadStream();

            uploadedBlob =
                await _blobStorageService.UploadReceiptAsync(
                    stream,
                    receipt.FileName,
                    receipt.ContentType,
                    cancellationToken);

            var now =
                _timeProvider.GetUtcNow().UtcDateTime;

            var appointmentReceipt =
                new AppointmentReceipt
                {
                    AppointmentPaymentId = payment.Id,
                    AppointmentId = appointmentId,
                    PatientId = patientId,
                    OriginalFileName =
                        Path.GetFileName(receipt.FileName),
                    BlobName =
                        uploadedBlob.BlobName,
                    ContainerName =
                        uploadedBlob.ContainerName,
                    ContentType =
                        receipt.ContentType,
                    SizeBytes =
                        receipt.Length,
                    Status =
                        AppointmentReceiptStatus.PendingVerification,
                    UploadedAtUtc = now
                };

            _repository.AddReceipt(
                appointmentReceipt);

            payment.Status =
                AppointmentPaymentStatus.ReceiptUnderVerification;

            payment.UpdatedAtUtc = now;

            await _repository.SaveChangesAsync(
                cancellationToken);

            return ToResponse(
                payment,
                payment.Appointment);
        }
        catch
        {
            if (uploadedBlob is not null)
            {
                try
                {
                    await _blobStorageService.DeleteAsync(
                        uploadedBlob.BlobName,
                        CancellationToken.None);
                }
                catch
                {
                    // Preserve the original failure.
                }
            }

            throw;
        }
    }

    public async Task<AppointmentPaymentResponseDto> VerifyReceiptAsync(
        Guid staffId,
        int appointmentId,
        AppointmentReceiptVerificationDto request,
        CancellationToken cancellationToken = default)
    {
        if (staffId == Guid.Empty)
        {
            throw new ArgumentException(
                "A valid staff identity is required.");
        }

        if (appointmentId <= 0)
        {
            throw new ArgumentException(
                "A valid appointment is required.");
        }

        var payment =
            await _repository.GetByAppointmentIdAsync(
                appointmentId,
                cancellationToken);

        if (payment is null ||
            payment.Appointment is null)
        {
            throw new KeyNotFoundException(
                "Payment information was not found for this appointment.");
        }

        if (payment.Method !=
            AppointmentPaymentMethod.BankTransfer)
        {
            throw new InvalidOperationException(
                "This appointment does not use bank transfer payment.");
        }

        if (payment.Status !=
            AppointmentPaymentStatus.ReceiptUnderVerification)
        {
            throw new InvalidOperationException(
                "There is no bank transfer receipt awaiting verification.");
        }

        var receipt =
            await _repository.GetLatestReceiptAsync(
                payment.Id,
                cancellationToken);

        if (receipt is null ||
            receipt.Status != AppointmentReceiptStatus.PendingVerification)
        {
            throw new InvalidOperationException(
                "There is no receipt awaiting verification.");
        }

        if (!request.Approved &&
            string.IsNullOrWhiteSpace(request.RejectionReason))
        {
            throw new ArgumentException(
                "A rejection reason is required when rejecting a receipt.");
        }

        var now =
            _timeProvider.GetUtcNow().UtcDateTime;

        receipt.ReviewedBy = staffId;
        receipt.ReviewedAtUtc = now;

        if (request.Approved)
        {
            receipt.Status =
                AppointmentReceiptStatus.Verified;

            receipt.RejectionReason = null;

            payment.Status =
                AppointmentPaymentStatus.Successful;
        }
        else
        {
            receipt.Status =
                AppointmentReceiptStatus.Rejected;

            receipt.RejectionReason =
                request.RejectionReason!.Trim();

            payment.Status =
                AppointmentPaymentStatus.AwaitingBankTransferReceipt;
        }

        payment.UpdatedAtUtc = now;

        try
        {
            await _repository.SaveChangesAsync(
                cancellationToken);
        }
        catch (DbUpdateException)
        {
            throw new InvalidOperationException(
                "The payment was updated by another request. Refresh and try again.");
        }

        return ToResponse(
            payment,
            payment.Appointment);
    }

    private static async Task ValidateReceiptContentAsync(IFormFile receipt, CancellationToken cancellationToken)
    {
        await using var stream = receipt.OpenReadStream();
        var header = new byte[8];
        var count = await stream.ReadAtLeastAsync(header, header.Length, throwOnEndOfStream: false, cancellationToken);
        var valid = receipt.ContentType.ToLowerInvariant() switch
        {
            "application/pdf" => count >= 5 && header.AsSpan(0, 5).SequenceEqual("%PDF-"u8),
            "image/jpeg" => count >= 3 && header[0] == 0xff && header[1] == 0xd8 && header[2] == 0xff,
            "image/png" => count >= 8 && header.AsSpan().SequenceEqual(new byte[] { 137, 80, 78, 71, 13, 10, 26, 10 }),
            _ => false
        };
        if (!valid) throw new ArgumentException("The receipt content is not a valid JPG, PNG, or PDF file. Please upload the correct receipt.");
    }

    private static bool TryParseMethod(
        string? value,
        out AppointmentPaymentMethod method)
    {
        method = default;

        var name = value?.Trim();

        if (string.IsNullOrWhiteSpace(name))
        {
            return false;
        }

        return Enum.TryParse(
            name,
            ignoreCase: true,
            out method)
            &&
            Enum.IsDefined(method);
    }

    private static AppointmentPaymentResponseDto ToResponse(
        AppointmentPayment payment,
        Appointment appointment)
    {
        return new AppointmentPaymentResponseDto
        {
            Id = payment.Id,
            AppointmentId = appointment.Id,
            AppointmentReference =
                appointment.AppointmentReference,
            Amount = payment.Amount,
            Method = payment.Method.ToString(),
            Status = payment.Status.ToString(),
            UpdatedAtUtc = DateTime.SpecifyKind(
                payment.UpdatedAtUtc,
                DateTimeKind.Utc)
        };
    }
}
