using AppointmentIntegration.Api.Clients;
using AppointmentIntegration.Api.DTOs.Appointment;
using AppointmentIntegration.Api.Exceptions;
using AppointmentIntegration.Api.Models;
using AppointmentIntegration.Api.Repositories;
using AppointmentIntegration.Api.Services.Interfaces;
using Microsoft.EntityFrameworkCore;

namespace AppointmentIntegration.Api.Services;

public class AppointmentBookingService : IAppointmentBookingService
{
    private readonly IAppointmentRepository _repository;
    private readonly DoctorPaymentClient _doctorPaymentClient;
    private readonly TimeProvider _timeProvider;

    public AppointmentBookingService(
        IAppointmentRepository repository,
        DoctorPaymentClient doctorPaymentClient,
        TimeProvider timeProvider)
    {
        _repository = repository;
        _doctorPaymentClient = doctorPaymentClient;
        _timeProvider = timeProvider;
    }

    public async Task<AppointmentResponseDto> BookAsync(
        Guid patientId,
        BookAppointmentRequestDto request,
        CancellationToken cancellationToken = default)
    {
        if (patientId == Guid.Empty)
        {
            throw new ArgumentException("A patient identity is required.");
        }

        var doctor = await _doctorPaymentClient.GetDoctorAsync(
            request.DoctorId,
            cancellationToken);

        if (doctor is null)
        {
            throw new SlotUnavailableException(
                "The selected doctor is unavailable.");
        }

        var slot = doctor.UpcomingSlots
            .FirstOrDefault(x => x.Id == request.SlotId);

        if (slot is null)
        {
            throw new SlotUnavailableException(
                "The selected appointment slot is no longer available.");
        }

        if (slot.StartUtc <= _timeProvider.GetUtcNow().UtcDateTime)
        {
            throw new SlotUnavailableException(
                "The selected appointment slot is no longer available.");
        }

        if (await _repository.SlotAlreadyBookedAsync(
                request.SlotId,
                cancellationToken))
        {
            throw new DuplicateBookingException(
                "This appointment slot has already been booked.");
        }

        var appointment = new Appointment
        {
            AppointmentReference = GenerateReference(),
            PatientId = patientId,
            DoctorId = doctor.DoctorId,
            DoctorName = doctor.FullName,
            DoctorAvailabilitySlotId = slot.Id,
            AppointmentStartUtc = slot.StartUtc,
            AppointmentEndUtc = slot.EndUtc,
            Status = AppointmentStatus.Booked,
            CreatedAtUtc = _timeProvider.GetUtcNow().UtcDateTime
        };

        await _repository.AddAsync(appointment, cancellationToken);

        try
        {
            await _repository.SaveChangesAsync(cancellationToken);
        }
        catch (DbUpdateException)
        {
            throw new DuplicateBookingException(
                "This appointment slot has already been booked.");
        }

        return new AppointmentResponseDto
        {
            Id = appointment.Id,
            AppointmentReference = appointment.AppointmentReference,
            PatientId = appointment.PatientId,
            DoctorId = appointment.DoctorId,
            DoctorName = appointment.DoctorName,
            SlotId = appointment.DoctorAvailabilitySlotId,
            AppointmentStartUtc = appointment.AppointmentStartUtc,
            AppointmentEndUtc = appointment.AppointmentEndUtc,
            Status = appointment.Status.ToString(),
            CreatedAtUtc = appointment.CreatedAtUtc
        };
    }

    private static string GenerateReference()
    {
        return $"CN-APT-{Guid.NewGuid():N}"[..20].ToUpperInvariant();
    }
}