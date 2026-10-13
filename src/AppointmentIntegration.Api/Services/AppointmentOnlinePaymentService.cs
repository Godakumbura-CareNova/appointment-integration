using System.Globalization;
using AppointmentIntegration.Api.Config;
using AppointmentIntegration.Api.DTOs.AppointmentPayment;
using AppointmentIntegration.Api.Exceptions;
using AppointmentIntegration.Api.Models;
using AppointmentIntegration.Api.Repositories;
using AppointmentIntegration.Api.Services.Interfaces;
using Microsoft.Extensions.Options;

namespace AppointmentIntegration.Api.Services;

public class AppointmentOnlinePaymentService
    : IAppointmentOnlinePaymentService
{
    private readonly IAppointmentPaymentRepository _repository;
    private readonly IAppointmentPaymentGateway _gateway;
    private readonly PayHereSettings _settings;
    private readonly TimeProvider _timeProvider;
    private readonly IAppointmentMutationScope? _mutations;

    public AppointmentOnlinePaymentService(
        IAppointmentPaymentRepository repository,
        IAppointmentPaymentGateway gateway,
        IOptions<PayHereSettings> settings,
        TimeProvider timeProvider,
        IAppointmentMutationScope? mutations = null)
    {
        _repository = repository;
        _gateway = gateway;
        _settings = settings.Value;
        _timeProvider = timeProvider;
        _mutations = mutations;
    }

    private int MaxAttempts =>
        Math.Max(1, _settings.MaxAttempts);

    public async Task<AppointmentOnlinePaymentSessionDto> StartAsync(
        Guid patientId,
        int appointmentId,
        StartAppointmentOnlinePaymentDto request,
        string? origin,
        CancellationToken cancellationToken = default)
    {
        if (patientId == Guid.Empty)
        {
            throw new ArgumentException(
                "A valid patient identity is required.");
        }

        ValidateBilling(request);
        await using var mutation = _mutations is null ? null : await _mutations.BeginAsync(appointmentId, cancellationToken);

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

        if (payment.Appointment.Status == AppointmentStatus.NoShow)
            throw new InvalidOperationException("Payment cannot be started for a No Show appointment.");
        if (payment.Appointment.Status == AppointmentStatus.Cancelled)
            throw new InvalidOperationException("Payment cannot be started for a cancelled appointment.");

        if (payment.Method !=
            AppointmentPaymentMethod.PaymentGateway)
        {
            throw new InvalidOperationException(
                "Payment gateway is not the selected payment method.");
        }

        if (payment.Status ==
            AppointmentPaymentStatus.Successful)
        {
            throw new InvalidOperationException(
                "This appointment has already been paid.");
        }

        if (payment.Status is not
            (AppointmentPaymentStatus.AwaitingGatewayPayment
            or AppointmentPaymentStatus.Failed))
        {
            throw new InvalidOperationException(
                "This payment cannot be paid through the gateway right now.");
        }

        if (payment.Amount <= 0)
        {
            throw new InvalidOperationException(
                "The appointment payment amount is invalid.");
        }

        var attempts =
            await _repository.GetOnlineAttemptsAsync(
                payment.Id,
                cancellationToken);

        var failedCount =
            attempts.Count(x =>
                x.Status ==
                    AppointmentOnlinePaymentAttemptStatus.Failed
                ||
                x.Status ==
                    AppointmentOnlinePaymentAttemptStatus.Cancelled);

        if (failedCount >= MaxAttempts)
        {
            throw new InvalidOperationException(
                $"Online payment has reached the maximum of {MaxAttempts} attempts.");
        }

        var now =
            _timeProvider.GetUtcNow().UtcDateTime;

        /*
         * Close any old attempt that was left pending before
         * starting another one.
         */
        foreach (var pending in attempts.Where(x =>
                     x.Status ==
                     AppointmentOnlinePaymentAttemptStatus.Pending))
        {
            pending.Status =
                AppointmentOnlinePaymentAttemptStatus.Cancelled;

            pending.FailureCode = "cancelled";
            pending.FailureMessage =
                "The previous payment attempt was not completed.";

            pending.CompletedAtUtc = now;
        }

        var attemptNumber =
            attempts.Count == 0
                ? 1
                : attempts.Max(x => x.AttemptNumber) + 1;

        var gatewayReference =
            $"{payment.Appointment.AppointmentReference}-{attemptNumber}";

        var frontend =
            GetFrontendBaseUrl(origin);

        var paymentPage =
            $"{frontend}/patient/appointments/{appointmentId}/payment";

        var customer =
            new GatewayCustomer(
                Clean(request.FirstName),
                Clean(request.LastName),
                Clean(request.Email),
                NormalizePhone(request.Phone!),
                Clean(request.Address),
                Clean(request.City),
                "Sri Lanka");

        var checkout =
            _gateway.CreateCheckout(
                new GatewayCheckoutRequest(
                    gatewayReference,
                    $"CareNova appointment {payment.Appointment.AppointmentReference}",
                    payment.Amount,
                    customer,
                    paymentPage,
                    paymentPage,
                    payment.Id.ToString(
                        CultureInfo.InvariantCulture)));

        var attempt =
            new AppointmentOnlinePaymentAttempt
            {
                AppointmentPaymentId = payment.Id,
                AppointmentId = appointmentId,
                PatientId = patientId,
                AttemptNumber = attemptNumber,
                GatewayReference = gatewayReference,
                Amount = payment.Amount,
                Currency = checkout.Currency,
                Status =
                    AppointmentOnlinePaymentAttemptStatus.Pending,
                IsTest = checkout.Sandbox,
                CreatedAtUtc = now
            };

        _repository.AddOnlineAttempt(attempt);

        payment.Status =
            AppointmentPaymentStatus.AwaitingGatewayPayment;

        payment.UpdatedAtUtc = now;

        await _repository.SaveChangesAsync(
            cancellationToken);

        if (mutation is not null) await mutation.CommitAsync(cancellationToken);
        return new AppointmentOnlinePaymentSessionDto
        {
            AttemptId = attempt.Id,
            AttemptNumber = attempt.AttemptNumber,
            Sandbox = checkout.Sandbox,
            MerchantId = checkout.MerchantId,
            GatewayOrderId = checkout.OrderId,
            Items = checkout.Items,
            Amount = checkout.Amount,
            Currency = checkout.Currency,
            Hash = checkout.Hash,
            NotifyUrl = checkout.NotifyUrl,
            ReturnUrl = checkout.ReturnUrl,
            CancelUrl = checkout.CancelUrl,
            FirstName = checkout.Customer.FirstName,
            LastName = checkout.Customer.LastName,
            Email = checkout.Customer.Email,
            Phone = checkout.Customer.Phone,
            Address = checkout.Customer.Address,
            City = checkout.Customer.City,
            Country = checkout.Customer.Country,
            Custom1 = checkout.Custom1,
            AppointmentReference =
                payment.Appointment.AppointmentReference
        };
    }

    public async Task<AppointmentOnlinePaymentResultDto> GetResultAsync(
        Guid patientId,
        int appointmentId,
        int attemptId,
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
            throw new KeyNotFoundException(
                "Payment information was not found.");
        }

        var attempts =
            await _repository.GetOnlineAttemptsAsync(
                payment.Id,
                cancellationToken);

        var attempt =
            attempts.SingleOrDefault(
                x => x.Id == attemptId);

        if (attempt is null)
        {
            throw new KeyNotFoundException(
                "Payment attempt was not found.");
        }

        return ToResult(
            payment,
            attempt,
            attempts);
    }

    public async Task<AppointmentOnlinePaymentResultDto> CancelAsync(
        Guid patientId,
        int appointmentId,
        int attemptId,
        CancellationToken cancellationToken = default)
    {
        await using var mutation = _mutations is null ? null : await _mutations.BeginAsync(appointmentId, cancellationToken);
        var payment =
            await _repository.GetByAppointmentAsync(
                patientId,
                appointmentId,
                cancellationToken);

        if (payment is null ||
            payment.Appointment is null)
        {
            throw new KeyNotFoundException(
                "Payment information was not found.");
        }

        var attempts =
            await _repository.GetOnlineAttemptsAsync(
                payment.Id,
                cancellationToken);

        var attempt =
            attempts.SingleOrDefault(
                x => x.Id == attemptId);

        if (attempt is null)
        {
            throw new KeyNotFoundException(
                "Payment attempt was not found.");
        }

        if (attempt.Status ==
            AppointmentOnlinePaymentAttemptStatus.Pending)
        {
            var now =
                _timeProvider.GetUtcNow().UtcDateTime;

            attempt.Status =
                AppointmentOnlinePaymentAttemptStatus.Cancelled;

            attempt.FailureCode = "cancelled";

            attempt.FailureMessage =
                "The payment was cancelled before completion.";

            attempt.CompletedAtUtc = now;

            // Closing another checkout must never undo a payment already confirmed by the gateway.
            if (payment.Status != AppointmentPaymentStatus.Successful)
            {
                payment.Status = AppointmentPaymentStatus.Failed;
                payment.UpdatedAtUtc = now;
            }

            await _repository.SaveChangesAsync(
                cancellationToken);
        }

        if (mutation is not null) await mutation.CommitAsync(cancellationToken);
        return ToResult(
            payment,
            attempt,
            attempts);
    }

    public async Task<bool> HandleNotificationAsync(
        IReadOnlyDictionary<string, string> form,
        CancellationToken cancellationToken = default)
    {
        var result =
            _gateway.ReadNotification(form);

        var attempt =
            await _repository.GetOnlineAttemptByGatewayReferenceAsync(
                result.OrderId,
                cancellationToken);

        if (attempt is null) return false;
        await using var mutation = _mutations is null ? null : await _mutations.BeginAsync(attempt.AppointmentId, cancellationToken);
        // Lock acquisition invalidates all tracked pre-lock state.
        attempt = await _repository.GetOnlineAttemptByGatewayReferenceAsync(result.OrderId, cancellationToken);

        if (attempt?.AppointmentPayment is not { } payment)
        {
            return false;
        }

        // A replaced checkout cannot undo a confirmed payment or pay a different method.
        if (payment.Status == AppointmentPaymentStatus.Successful)
        {
            return true;
        }
        if (payment.Method != AppointmentPaymentMethod.PaymentGateway)
        {
            // After cancellation, retain actual money received for the original checkout.
            // Its amount belongs to that attempt, not the replacement cash/bank payment.
            if (payment.Appointment?.Status == AppointmentStatus.Cancelled && result.StatusCode == 2
                && attempt.Status != AppointmentOnlinePaymentAttemptStatus.Succeeded
                && Math.Abs(result.Amount - attempt.Amount) <= 0.001m
                && string.Equals(result.Currency, attempt.Currency, StringComparison.OrdinalIgnoreCase))
            {
                var receivedAt = _timeProvider.GetUtcNow().UtcDateTime;
                attempt.Status = AppointmentOnlinePaymentAttemptStatus.Succeeded;
                attempt.GatewayPaymentId = Truncate(result.PaymentId, 50);
                attempt.GatewayPaymentMethod = Truncate(result.Method, 30);
                attempt.CompletedAtUtc = receivedAt; attempt.FailureCode = null; attempt.FailureMessage = null;
                _mutations?.RecordLateGatewayPayment(attempt.AppointmentId, payment.Id, attempt.Id, receivedAt);
                await _repository.SaveChangesAsync(cancellationToken);
                if (mutation is not null) await mutation.CommitAsync(cancellationToken);
                return true;
            }
            if (payment.Appointment?.Status == AppointmentStatus.Cancelled && attempt.Status == AppointmentOnlinePaymentAttemptStatus.Succeeded) return true;
            return false;
        }

        /*
         * Ignore duplicate final callbacks.
         */
        if (attempt.Status is
            AppointmentOnlinePaymentAttemptStatus.Succeeded
            or AppointmentOnlinePaymentAttemptStatus.Failed)
        {
            return true;
        }

        var now =
            _timeProvider.GetUtcNow().UtcDateTime;

        attempt.GatewayPaymentId =
            Truncate(result.PaymentId, 50);

        attempt.GatewayPaymentMethod =
            Truncate(result.Method, 30);

        /*
         * Never trust a successful status alone.
         * Amount and currency must also match.
         */
        if (Math.Abs(
                result.Amount -
                attempt.Amount) > 0.001m
            || Math.Abs(payment.Amount - attempt.Amount) > 0.001m
            ||
            !string.Equals(
                result.Currency,
                attempt.Currency,
                StringComparison.OrdinalIgnoreCase))
        {
            FailAttempt(
                attempt,
                payment,
                "verification_failed",
                "The payment amount or currency could not be verified.",
                now);

            await _repository.SaveChangesAsync(
                cancellationToken);
            if (mutation is not null) await mutation.CommitAsync(cancellationToken);
            return true;
        }

        switch (result.StatusCode)
        {
            // PayHere success
            case 2:
                attempt.Status =
                    AppointmentOnlinePaymentAttemptStatus.Succeeded;

                attempt.FailureCode = null;
                attempt.FailureMessage = null;
                attempt.CompletedAtUtc = now;

                payment.Status =
                    AppointmentPaymentStatus.Successful;
                payment.ConfirmedAtUtc ??= now;

                payment.UpdatedAtUtc = now;
                if (payment.Appointment?.Status == AppointmentStatus.Cancelled)
                    _mutations?.RecordLateGatewayPayment(attempt.AppointmentId, payment.Id, attempt.Id, now);
                break;

            // Cancelled
            case -1:
                attempt.Status =
                    AppointmentOnlinePaymentAttemptStatus.Cancelled;

                attempt.FailureCode = "-1";

                attempt.FailureMessage =
                    string.IsNullOrWhiteSpace(result.StatusMessage)
                        ? "The payment was cancelled."
                        : result.StatusMessage;

                attempt.CompletedAtUtc = now;

                payment.Status =
                    AppointmentPaymentStatus.Failed;

                payment.UpdatedAtUtc = now;
                break;

            // Failed
            case -2:
                FailAttempt(
                    attempt,
                    payment,
                    "-2",
                    string.IsNullOrWhiteSpace(result.StatusMessage)
                        ? "The payment gateway transaction failed."
                        : result.StatusMessage,
                    now);
                break;

            // Chargeback
            case -3:
                FailAttempt(
                    attempt,
                    payment,
                    "-3",
                    "The payment was charged back.",
                    now);
                break;

            // PayHere still processing
            default:
                await _repository.SaveChangesAsync(
                    cancellationToken);
                if (mutation is not null) await mutation.CommitAsync(cancellationToken);
                return true;
        }

        await _repository.SaveChangesAsync(
            cancellationToken);
        if (mutation is not null) await mutation.CommitAsync(cancellationToken);
        return true;
    }

    private static void FailAttempt(
        AppointmentOnlinePaymentAttempt attempt,
        AppointmentPayment payment,
        string code,
        string message,
        DateTime now)
    {
        attempt.Status =
            AppointmentOnlinePaymentAttemptStatus.Failed;

        attempt.FailureCode =
            Truncate(code, 100);

        attempt.FailureMessage =
            Truncate(message, 500);

        attempt.CompletedAtUtc = now;

        payment.Status =
            AppointmentPaymentStatus.Failed;

        payment.UpdatedAtUtc = now;
    }

    private AppointmentOnlinePaymentResultDto ToResult(
        AppointmentPayment payment,
        AppointmentOnlinePaymentAttempt attempt,
        IReadOnlyCollection<AppointmentOnlinePaymentAttempt> attempts)
    {
        var failedCount =
            attempts.Count(x =>
                x.Status is
                    AppointmentOnlinePaymentAttemptStatus.Failed
                    or AppointmentOnlinePaymentAttemptStatus.Cancelled);

        var outcome =
            attempt.Status switch
            {
                AppointmentOnlinePaymentAttemptStatus.Succeeded =>
                    "Succeeded",

                AppointmentOnlinePaymentAttemptStatus.Failed =>
                    "Failed",

                AppointmentOnlinePaymentAttemptStatus.Cancelled =>
                    "Cancelled",

                _ => "Processing"
            };

        var message =
            attempt.Status switch
            {
                AppointmentOnlinePaymentAttemptStatus.Succeeded =>
                    "Your appointment payment was successful.",

                AppointmentOnlinePaymentAttemptStatus.Failed =>
                    $"Payment failed: {attempt.FailureMessage}",

                AppointmentOnlinePaymentAttemptStatus.Cancelled =>
                    "The payment was cancelled.",

                _ =>
                    "We are waiting for the payment gateway to confirm the transaction."
            };

        return new AppointmentOnlinePaymentResultDto
        {
            Outcome = outcome,
            Message = message,
            CanRetry =
                payment.Appointment?.Status != AppointmentStatus.Cancelled &&
                payment.Status !=
                    AppointmentPaymentStatus.Successful
                &&
                failedCount < MaxAttempts,
            IsTest = attempt.IsTest,
            TransactionReference =
                attempt.GatewayReference,
            FailureCode =
                attempt.FailureCode,
            Payment =
                new AppointmentPaymentResponseDto
                {
                    Id = payment.Id,
                    AppointmentId = payment.AppointmentId,
                    AppointmentReference =
                        payment.Appointment?
                            .AppointmentReference
                        ?? string.Empty,
                    Amount = payment.Amount,
                    Method =
                        payment.Method.ToString(),
                    Status =
                        payment.Status.ToString(),
                    UpdatedAtUtc =
                        DateTime.SpecifyKind(
                            payment.UpdatedAtUtc,
                            DateTimeKind.Utc)
                }
        };
    }

    private static void ValidateBilling(
        StartAppointmentOnlinePaymentDto request)
    {
        if (string.IsNullOrWhiteSpace(request.FirstName))
        {
            throw new ArgumentException(
                "Enter your first name.");
        }

        if (string.IsNullOrWhiteSpace(request.LastName))
        {
            throw new ArgumentException(
                "Enter your last name.");
        }

        if (string.IsNullOrWhiteSpace(request.Email) ||
            !request.Email.Contains('@'))
        {
            throw new ArgumentException(
                "Enter a valid email address.");
        }

        if (string.IsNullOrWhiteSpace(request.Phone))
        {
            throw new ArgumentException(
                "Enter your phone number.");
        }

        if (string.IsNullOrWhiteSpace(request.Address))
        {
            throw new ArgumentException(
                "Enter your address.");
        }

        if (string.IsNullOrWhiteSpace(request.City))
        {
            throw new ArgumentException(
                "Enter your city.");
        }
    }

    private string GetFrontendBaseUrl(
        string? origin)
    {
        var configured =
            _settings.FrontendBaseUrl?
                .Trim()
                .TrimEnd('/');

        if (!string.IsNullOrWhiteSpace(configured))
        {
            return configured;
        }

        if (Uri.TryCreate(
                origin,
                UriKind.Absolute,
                out var uri)
            &&
            (uri.Scheme == Uri.UriSchemeHttps ||
             uri.Scheme == Uri.UriSchemeHttp))
        {
            return uri.GetLeftPart(
                UriPartial.Authority);
        }

        return "http://localhost:3000";
    }

    private static string NormalizePhone(
        string phone)
    {
        var digits =
            new string(
                phone.Where(char.IsDigit)
                    .ToArray());

        if (digits.StartsWith(
                "0094",
                StringComparison.Ordinal))
        {
            digits = digits[2..];
        }

        if (digits.StartsWith(
                "94",
                StringComparison.Ordinal)
            &&
            digits.Length == 11)
        {
            return "0" + digits[2..];
        }

        return digits;
    }

    private static string Clean(
        string? value)
    {
        return (value ?? string.Empty).Trim();
    }

    private static string? Truncate(
        string? value,
        int maxLength)
    {
        if (value is null)
        {
            return null;
        }

        return value.Length <= maxLength
            ? value
            : value[..maxLength];
    }
}
