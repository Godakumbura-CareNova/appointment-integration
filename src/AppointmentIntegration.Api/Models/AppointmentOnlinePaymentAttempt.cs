using System.ComponentModel.DataAnnotations;

namespace AppointmentIntegration.Api.Models;

public enum AppointmentOnlinePaymentAttemptStatus
{
    Pending = 1,
    Succeeded = 2,
    Failed = 3,
    Cancelled = 4
}

public class AppointmentOnlinePaymentAttempt
{
    public int Id { get; set; }

    public int AppointmentPaymentId { get; set; }

    public AppointmentPayment? AppointmentPayment { get; set; }

    public int AppointmentId { get; set; }

    public Guid PatientId { get; set; }

    public int AttemptNumber { get; set; }

    [MaxLength(100)]
    public string GatewayReference { get; set; } = string.Empty;

    [MaxLength(50)]
    public string? GatewayPaymentId { get; set; }

    [MaxLength(30)]
    public string? GatewayPaymentMethod { get; set; }

    public decimal Amount { get; set; }

    [MaxLength(3)]
    public string Currency { get; set; } = "LKR";

    public AppointmentOnlinePaymentAttemptStatus Status { get; set; }

    public bool IsTest { get; set; }

    [MaxLength(100)]
    public string? FailureCode { get; set; }

    [MaxLength(500)]
    public string? FailureMessage { get; set; }

    public DateTime CreatedAtUtc { get; set; }

    public DateTime? CompletedAtUtc { get; set; }
}