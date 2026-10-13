using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Models;
using Microsoft.EntityFrameworkCore;

namespace AppointmentIntegration.Api.Repositories;

public class AppointmentPaymentRepository
    : IAppointmentPaymentRepository
{
    private readonly AppDbContext _dbContext;

    public AppointmentPaymentRepository(
        AppDbContext dbContext)
    {
        _dbContext = dbContext;
    }

    public Task<AppointmentPayment?> GetByAppointmentAsync(
        Guid patientId,
        int appointmentId,
        CancellationToken cancellationToken = default)
    {
        return _dbContext.AppointmentPayments
            .Include(x => x.Appointment)
            .SingleOrDefaultAsync(
                x =>
                    x.AppointmentId == appointmentId &&
                    x.PatientId == patientId,
                cancellationToken);
    }

    public Task<AppointmentPayment?> GetByAppointmentIdAsync(
        int appointmentId,
        CancellationToken cancellationToken = default)
    {
        return _dbContext.AppointmentPayments
            .Include(x => x.Appointment)
            .SingleOrDefaultAsync(
                x => x.AppointmentId == appointmentId,
                cancellationToken);
    }

    public Task<Appointment?> GetAppointmentAsync(
        Guid patientId,
        int appointmentId,
        CancellationToken cancellationToken = default)
    {
        return _dbContext.Appointments
            .SingleOrDefaultAsync(
                x =>
                    x.Id == appointmentId &&
                    x.PatientId == patientId,
                cancellationToken);
    }

    public Task<AppointmentReceipt?> GetLatestReceiptAsync(
        int appointmentPaymentId,
        CancellationToken cancellationToken = default)
    {
        return _dbContext.AppointmentReceipts
            .Where(x =>
                x.AppointmentPaymentId == appointmentPaymentId)
            .OrderByDescending(x => x.UploadedAtUtc)
            .ThenByDescending(x => x.Id)
            .FirstOrDefaultAsync(cancellationToken);
    }

    public Task<List<AppointmentReceipt>> GetPendingReceiptsAsync(
        CancellationToken cancellationToken = default)
    {
        return _dbContext.AppointmentReceipts
            .Include(x => x.AppointmentPayment)
            .ThenInclude(x => x!.Appointment)
            .Where(x =>
                x.Status ==
                AppointmentReceiptStatus.PendingVerification)
            .OrderBy(x => x.UploadedAtUtc)
            .ToListAsync(cancellationToken);
    }

    public Task<AppointmentReceipt?> GetReceiptByIdAsync(
        int receiptId,
        CancellationToken cancellationToken = default)
    {
        return _dbContext.AppointmentReceipts
            .Include(x => x.AppointmentPayment)
            .ThenInclude(x => x!.Appointment)
            .SingleOrDefaultAsync(
                x => x.Id == receiptId,
                cancellationToken);
    }

    public Task<List<AppointmentOnlinePaymentAttempt>> GetOnlineAttemptsAsync(
        int appointmentPaymentId,
        CancellationToken cancellationToken = default)
    {
        return _dbContext.AppointmentOnlinePaymentAttempts
            .Where(x =>
                x.AppointmentPaymentId == appointmentPaymentId)
            .OrderBy(x => x.AttemptNumber)
            .ToListAsync(cancellationToken);
    }

    public Task<AppointmentOnlinePaymentAttempt?> GetOnlineAttemptByGatewayReferenceAsync(
        string gatewayReference,
        CancellationToken cancellationToken = default)
    {
        return _dbContext.AppointmentOnlinePaymentAttempts
            .Include(x => x.AppointmentPayment)
            .ThenInclude(x => x!.Appointment)
            .SingleOrDefaultAsync(
                x => x.GatewayReference == gatewayReference,
                cancellationToken);
    }

    public void Add(
        AppointmentPayment payment)
    {
        _dbContext.AppointmentPayments.Add(payment);
    }

    public void AddReceipt(
        AppointmentReceipt receipt)
    {
        _dbContext.AppointmentReceipts.Add(receipt);
    }

    public void AddOnlineAttempt(
        AppointmentOnlinePaymentAttempt attempt)
    {
        _dbContext.AppointmentOnlinePaymentAttempts.Add(attempt);
    }

    public Task SaveChangesAsync(
        CancellationToken cancellationToken = default)
    {
        return _dbContext.SaveChangesAsync(
            cancellationToken);
    }
}