using System.ComponentModel.DataAnnotations;

namespace AppointmentIntegration.Api.Models;

public enum AppointmentReceiptStatus
{
    PendingVerification = 1,
    Verified = 2,
    Rejected = 3
}

public class AppointmentReceipt
{
    public int Id { get; set; }

    public int AppointmentPaymentId { get; set; }

    public AppointmentPayment? AppointmentPayment { get; set; }

    public int AppointmentId { get; set; }

    public Guid PatientId { get; set; }

    [MaxLength(255)]
    public string OriginalFileName { get; set; } = string.Empty;

    [MaxLength(500)]
    public string BlobName { get; set; } = string.Empty;

    [MaxLength(100)]
    public string ContainerName { get; set; } = string.Empty;

    [MaxLength(100)]
    public string ContentType { get; set; } = string.Empty;

    public long SizeBytes { get; set; }

    public AppointmentReceiptStatus Status { get; set; }

    public DateTime UploadedAtUtc { get; set; }

    public Guid? ReviewedBy { get; set; }

    public DateTime? ReviewedAtUtc { get; set; }

    [MaxLength(500)]
    public string? RejectionReason { get; set; }
    // The rejected receipt itself is the durable patient notification (one per receipt).
    public DateTime? PatientNotificationReadAtUtc { get; set; }
}
