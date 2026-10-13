namespace AppointmentIntegration.Api.DTOs.AppointmentPayment;

public class AppointmentReceiptVerificationDto
{
    public bool Approved { get; set; }

    public string? RejectionReason { get; set; }
}