namespace AppointmentIntegration.Api.Exceptions;

public class SlotUnavailableException : Exception
{
    public SlotUnavailableException(string message)
        : base(message)
    {
    }
}