namespace AppointmentIntegration.Api.Models;

public class AppointmentPayment
{
    public int Id { get; set; }

    public int AppointmentId { get; set; }

    public Appointment? Appointment { get; set; }

    public Guid PatientId { get; set; }

    public decimal Amount { get; set; }

    public AppointmentPaymentMethod Method { get; set; }

    public AppointmentPaymentStatus Status { get; set; }

    public DateTime CreatedAtUtc { get; set; }

    public DateTime UpdatedAtUtc { get; set; }
    // Authoritative success time; null for legacy payments whose date cannot be proven.
    public DateTime? ConfirmedAtUtc { get; set; }
}
