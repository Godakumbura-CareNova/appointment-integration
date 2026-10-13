namespace AppointmentIntegration.Api.DTOs.Dashboard;

public sealed record AdminAppointmentDashboardDto(int TotalAppointments, IReadOnlyDictionary<string, int> StatusCounts,
    int TodayCount, int UpcomingCount, IReadOnlyList<DashboardAppointment> RecentAppointments, DateTime GeneratedAtUtc);
public sealed record AdminAppointmentPaymentDashboardDto(int TotalPayments, IReadOnlyDictionary<string, int> StatusCounts,
    AppointmentDashboardQueue PendingTransfers, IReadOnlyList<AppointmentDashboardPayment> RecentPayments,
    AppointmentDashboardIncome Income, DateTime GeneratedAtUtc);
