using System.Text.RegularExpressions;
using AppointmentIntegration.Api.DTOs.PublicContent;
using FluentValidation;
namespace AppointmentIntegration.Api.Validators;

public sealed class PharmacyInformationValidator : AbstractValidator<PharmacyInformationDto>
{
    public static readonly string[] Days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
    public static bool ValidPhone(string? value) => string.IsNullOrWhiteSpace(value) ||
        (Regex.IsMatch(value, @"^\+?[\d\s().-]+$") && value.Count(char.IsDigit) is >= 7 and <= 15);
    public static bool ValidMap(string? value) => string.IsNullOrWhiteSpace(value) ||
        (Uri.TryCreate(value, UriKind.Absolute, out var uri) && uri.Scheme == "https" &&
         uri.Host is "www.google.com" or "maps.google.com" && (uri.AbsolutePath == "/maps/embed" || uri.AbsolutePath.StartsWith("/maps/embed/")) &&
         uri.UserInfo.Length == 0 && uri.IsDefaultPort);
    public static bool ValidImage(string? value) => value is not null && Regex.IsMatch(value, @"^/uploads/pharmacy-information/[a-f0-9]{32}\.(jpg|png|webp)$");
    public PharmacyInformationValidator()
    {
        RuleFor(x => x.Introduction).NotEmpty().MaximumLength(3000);
        RuleFor(x => x.Background).MaximumLength(6000);
        RuleFor(x => x.Mission).MaximumLength(2000);
        RuleFor(x => x.Vision).MaximumLength(2000);
        RuleFor(x => x.Address).MaximumLength(1000);
        RuleFor(x => x.LocationDescription).MaximumLength(2000);
        RuleFor(x => x.Phone).MaximumLength(40).Must(ValidPhone).WithMessage("Enter a valid phone number.");
        RuleFor(x => x.Email).MaximumLength(254).EmailAddress().Matches(@"^[^\s@]+@[^\s@]+\.[^\s@]+$").When(x => !string.IsNullOrWhiteSpace(x.Email));
        RuleFor(x => x.MapEmbedUrl).MaximumLength(3000).Must(ValidMap).WithMessage("Use an HTTPS Google Maps embed URL.");
        RuleFor(x => x.Services).NotNull().Must(x => x is { Count: <= 12 });
        RuleForEach(x => x.Services).NotNull();
        RuleForEach(x => x.Services).ChildRules(service => {
            service.RuleFor(x => x.Title).NotEmpty().MaximumLength(120);
            service.RuleFor(x => x.Description).NotEmpty().MaximumLength(1000);
        });
        RuleFor(x => x.OpeningHours).NotNull().Must(x => x is { Count: <= 7 } && x.All(h => h is not null) && x.Select(h => h.Day).Distinct().Count() == x.Count);
        RuleForEach(x => x.OpeningHours).NotNull();
        RuleForEach(x => x.OpeningHours).ChildRules(hours => {
            hours.RuleFor(x => x.Day).Must(day => Days.Contains(day));
            hours.RuleFor(x => x.Hours).NotEmpty().MaximumLength(120);
        });
        RuleFor(x => x.Images).NotNull().Must(x => x is { Count: <= 20 });
        RuleForEach(x => x.Images).NotNull();
        RuleForEach(x => x.Images).ChildRules(image => {
            image.RuleFor(x => x.Url).Must(ValidImage).WithMessage("Select a photograph uploaded to the pharmacy information service.");
            image.RuleFor(x => x.Caption).NotEmpty().MaximumLength(200);
        });
    }
}
