using AppointmentIntegration.Api.DTOs.PublicContent;
using FluentValidation;
namespace AppointmentIntegration.Api.Validators;
public sealed class ContactInquiryValidator : AbstractValidator<ContactInquiryRequestDto>
{
    public ContactInquiryValidator()
    {
        RuleFor(x => x.Name).NotEmpty().MaximumLength(120);
        RuleFor(x => x.Email).NotEmpty().MaximumLength(254).EmailAddress().Matches(@"^[^\s@]+@[^\s@]+\.[^\s@]+$");
        RuleFor(x => x.Phone).MaximumLength(40).Must(PharmacyInformationValidator.ValidPhone).WithMessage("Enter a valid phone number.");
        RuleFor(x => x.Subject).NotEmpty().MaximumLength(200);
        RuleFor(x => x.Message).NotEmpty().MaximumLength(5000);
    }
}
