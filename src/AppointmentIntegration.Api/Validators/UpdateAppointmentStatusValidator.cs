using AppointmentIntegration.Api.DTOs.Appointment;
using FluentValidation;

namespace AppointmentIntegration.Api.Validators;

public sealed class UpdateAppointmentStatusValidator : AbstractValidator<UpdateAppointmentStatusDto>
{
    public UpdateAppointmentStatusValidator()
    {
        RuleFor(x => x.Status).Must(x => x is "Confirmed" or "Completed" or "NoShow").WithMessage("Choose a valid appointment status.");
        RuleFor(x => x.ExpectedStatus).Must(x => x is "Booked" or "Confirmed" or "Completed" or "NoShow" or "Cancelled").WithMessage("Refresh the appointment before updating it.");
        RuleFor(x => x.ExpectedUpdatedAtUtc).Must(x => x is null || x.Value.Kind == DateTimeKind.Utc).WithMessage("The appointment update time must be UTC.");
    }
}
