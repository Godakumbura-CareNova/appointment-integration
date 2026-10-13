namespace AppointmentIntegration.Api.Exceptions;

public class DuplicateBookingException : Exception
{
    public DuplicateBookingException(string message)
        : base(message)
    {
    }
}