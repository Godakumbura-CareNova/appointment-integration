namespace AppointmentIntegration.Api.Services.Interfaces;

public sealed record GatewayCustomer(
    string FirstName,
    string LastName,
    string Email,
    string Phone,
    string Address,
    string City,
    string Country);

public sealed record GatewayCheckoutRequest(
    string OrderId,
    string ItemsDescription,
    decimal Amount,
    GatewayCustomer Customer,
    string ReturnUrl,
    string CancelUrl,
    string Custom1);

public sealed record GatewayCheckout(
    bool Sandbox,
    string MerchantId,
    string OrderId,
    string Items,
    string Amount,
    string Currency,
    string Hash,
    string NotifyUrl,
    string ReturnUrl,
    string CancelUrl,
    GatewayCustomer Customer,
    string Custom1);

public sealed record GatewayNotification(
    string OrderId,
    string? PaymentId,
    decimal Amount,
    string Currency,
    int StatusCode,
    string? StatusMessage,
    string? Method);

public interface IAppointmentPaymentGateway
{
    bool IsConfigured { get; }

    bool IsTestMode { get; }

    string Currency { get; }

    GatewayCheckout CreateCheckout(
        GatewayCheckoutRequest request);

    GatewayNotification ReadNotification(
        IReadOnlyDictionary<string, string> form);
}