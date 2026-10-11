using System.ComponentModel.DataAnnotations;

namespace AppointmentIntegration.Api.DTOs.Cancellation;

public sealed class CancelAppointmentRequestDto
{
    [Required, StringLength(64, MinimumLength = 64)] public string ExpectedVersion { get; set; } = "";
    public bool AcknowledgeNoRefund { get; set; }
    [StringLength(500)] public string? Reason { get; set; }
}
