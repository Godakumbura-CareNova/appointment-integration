namespace AppointmentIntegration.Api.Exceptions;

public sealed class InvalidAppointmentStatusTransitionException() : Exception("This status change is not allowed at this time. Refresh the appointment and try again.");
