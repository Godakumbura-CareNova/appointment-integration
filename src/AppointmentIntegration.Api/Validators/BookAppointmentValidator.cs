using AppointmentIntegration.Api.DTOs.Appointment;
using FluentValidation;

namespace AppointmentIntegration.Api.Validators;

public class BookAppointmentValidator
    : AbstractValidator<BookAppointmentRequestDto>
{
    public BookAppointmentValidator()
    {
        RuleFor(x => x.DoctorId)
            .NotEmpty()
            .WithMessage("Please select a doctor.");

        RuleFor(x => x.SlotId)
            .GreaterThan(0)
            .WithMessage("Please select an appointment time slot.");
    }
}