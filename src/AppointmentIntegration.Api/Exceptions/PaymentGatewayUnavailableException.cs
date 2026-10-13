namespace AppointmentIntegration.Api.Exceptions;

public class PaymentGatewayUnavailableException : Exception
{
    public PaymentGatewayUnavailableException(string message)
        : base(message)
    {
    }
}