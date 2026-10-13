namespace AppointmentIntegration.Api.DTOs.Cancellation;

public sealed record CancellationEligibilityDto(int AppointmentId, bool Allowed, string ReasonCode, string Message,
    string RefundOutcome, decimal RefundAmount, bool RequiresNoRefundAcknowledgement, string Version, CancellationResponseDto? Cancellation);
