namespace AppointmentIntegration.Api.DTOs.Appointment;

public sealed record DoctorAppointmentStatistics(int Today, int Upcoming, int Completed, int PatientCount);
public sealed record DoctorAppointmentListDto(IReadOnlyList<DoctorAppointmentDto> Appointments, DoctorAppointmentStatistics Statistics, bool ContactsUnavailable);
public sealed record AppointmentStatusResultDto(int Id, string Status, DateTime UpdatedAtUtc);
