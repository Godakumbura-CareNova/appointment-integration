namespace AppointmentIntegration.Api.DTOs.Dashboard;

public record DashboardAppointment(int Id, string Reference, string DoctorName, DateTime StartUtc, string Status, string? PaymentMethod, string? PaymentStatus);
public record PatientAppointmentDashboard(int UpcomingCount, IReadOnlyList<DashboardAppointment> Appointments, IReadOnlyDictionary<string, int> PaymentStatusCounts, DateTime GeneratedAtUtc);
public record AppointmentDashboardPayment(int Id, int AppointmentId, string Reference, decimal Amount, string Method, string Status, DateTime? ConfirmedAtUtc, DateTime UpdatedAtUtc);
public record AppointmentDashboardQueue(int TotalCount, IReadOnlyList<AppointmentDashboardPayment> Items);
public record AppointmentDashboardIncome(decimal TodayAmount, decimal MonthAmount, int UndatedSuccessfulCount, decimal UndatedSuccessfulAmount, string Currency, string TimeZone, DateTime AsOfUtc);
public record StaffAppointmentPaymentDashboard(AppointmentDashboardQueue PendingTransfers, IReadOnlyList<AppointmentDashboardPayment> RecentPayments, AppointmentDashboardIncome Income, DateTime GeneratedAtUtc);
