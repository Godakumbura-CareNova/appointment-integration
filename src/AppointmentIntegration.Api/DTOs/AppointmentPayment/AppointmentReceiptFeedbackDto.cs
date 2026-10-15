namespace AppointmentIntegration.Api.DTOs.AppointmentPayment;

public sealed record AppointmentReceiptFeedbackDto(string Status, string? RejectionReason, DateTime? ReviewedAtUtc);
