namespace AppointmentIntegration.Api.DTOs.Cancellation;

public sealed record CancellationResponseDto(int AppointmentId, string AppointmentReference, string Status, DateTime CancelledAtUtc,
    string RefundOutcome, decimal RefundAmount, string? RefundStatus, string? Reason, string Message);
