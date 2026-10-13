using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using AppointmentIntegration.Api.Config;
using AppointmentIntegration.Api.Exceptions;
using AppointmentIntegration.Api.Services.Interfaces;
using Microsoft.Extensions.Options;

namespace AppointmentIntegration.Api.Services;

public sealed class PayHerePaymentGateway
    : IAppointmentPaymentGateway
{
    public const string UnavailableMessage =
        "The online payment service is unavailable right now. Please try again shortly.";

    private readonly PayHereSettings _settings;
    private readonly ILogger<PayHerePaymentGateway> _logger;

    public PayHerePaymentGateway(
        IOptions<PayHereSettings> settings,
        ILogger<PayHerePaymentGateway> logger)
    {
        _settings = settings.Value;
        _logger = logger;
    }

    public bool IsConfigured => _settings.IsConfigured;

    public bool IsTestMode => _settings.Sandbox;

    public string Currency =>
        string.IsNullOrWhiteSpace(_settings.Currency)
            ? "LKR"
            : _settings.Currency.Trim().ToUpperInvariant();

    public GatewayCheckout CreateCheckout(
        GatewayCheckoutRequest request)
    {
        if (!_settings.IsConfigured)
        {
            _logger.LogError(
                "PayHere is not configured correctly.");

            throw new PaymentGatewayUnavailableException(
                UnavailableMessage);
        }

        var amount = FormatAmount(request.Amount);

        var hash = Md5(
            _settings.MerchantId
            + request.OrderId
            + amount
            + Currency
            + Md5(_settings.MerchantSecret));

        return new GatewayCheckout(
            _settings.Sandbox,
            _settings.MerchantId,
            request.OrderId,
            request.ItemsDescription,
            amount,
            Currency,
            hash,
            _settings.NotifyUrl,
            request.ReturnUrl,
            request.CancelUrl,
            request.Customer,
            request.Custom1);
    }

    public GatewayNotification ReadNotification(
        IReadOnlyDictionary<string, string> form)
    {
        if (!_settings.IsConfigured)
        {
            throw new InvalidWebhookSignatureException(
                "PayHere is not configured.");
        }

        string Field(string name)
        {
            if (form.TryGetValue(name, out var value) &&
                !string.IsNullOrWhiteSpace(value))
            {
                return value.Trim();
            }

            throw new InvalidWebhookSignatureException(
                $"The payment result has no {name}.");
        }

        var merchantId = Field("merchant_id");
        var orderId = Field("order_id");
        var amount = Field("payhere_amount");
        var currency = Field("payhere_currency");
        var statusCode = Field("status_code");
        var signature = Field("md5sig");

        var expected = Md5(
            merchantId
            + orderId
            + amount
            + currency
            + statusCode
            + Md5(_settings.MerchantSecret));

        if (!string.Equals(
                merchantId,
                _settings.MerchantId,
                StringComparison.Ordinal)
            ||
            !CryptographicOperations.FixedTimeEquals(
                Encoding.ASCII.GetBytes(expected),
                Encoding.ASCII.GetBytes(signature.ToUpperInvariant())))
        {
            throw new InvalidWebhookSignatureException(
                "The payment result signature is not valid.");
        }

        if (!decimal.TryParse(
                amount,
                NumberStyles.Number,
                CultureInfo.InvariantCulture,
                out var paidAmount)
            ||
            !int.TryParse(
                statusCode,
                NumberStyles.AllowLeadingSign,
                CultureInfo.InvariantCulture,
                out var code))
        {
            throw new InvalidWebhookSignatureException(
                "The payment result is not in the expected format.");
        }

        return new GatewayNotification(
            orderId,
            form.GetValueOrDefault("payment_id"),
            paidAmount,
            currency.ToUpperInvariant(),
            code,
            form.GetValueOrDefault("status_message"),
            form.GetValueOrDefault("method"));
    }

    public static string FormatAmount(decimal amount)
    {
        return amount.ToString(
            "0.00",
            CultureInfo.InvariantCulture);
    }

    public static string Md5(string value)
    {
        return Convert.ToHexString(
            MD5.HashData(
                Encoding.UTF8.GetBytes(value)));
    }
}