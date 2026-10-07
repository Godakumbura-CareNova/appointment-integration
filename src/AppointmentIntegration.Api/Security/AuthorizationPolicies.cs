namespace AppointmentIntegration.Api.Security;

public static class AuthorizationPolicies
{
    public const string PharmacyStaff = "PharmacyStaff";

    public static IServiceCollection AddAuthorizationPolicies(
        this IServiceCollection services)
    {
        services.AddAuthorization(options =>
        {
            options.AddPolicy(
                PharmacyStaff,
                policy => policy.RequireRole(PharmacyStaff));
        });

        return services;
    }
}