namespace AppointmentIntegration.Api.Exceptions;

public class InvalidWebhookSignatureException : Exception
{
    public InvalidWebhookSignatureException(string message)
        : base(message)
    {
    }
}