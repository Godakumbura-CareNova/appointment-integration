using System.Net;
using System.Text;
using AppointmentIntegration.Api.Clients;
using AppointmentIntegration.Api.DTOs.Appointment;
using AppointmentIntegration.Api.Exceptions;
using AppointmentIntegration.Api.Models;
using AppointmentIntegration.Api.Repositories;
using AppointmentIntegration.Api.Services;
using Microsoft.AspNetCore.Http;
using Moq;

namespace AppointmentIntegration.Api.Tests.Unit;

public class AppointmentBookingServiceTests
{
    private static readonly Guid PatientId =
        Guid.Parse("11111111-1111-1111-1111-111111111111");

    private static readonly Guid DoctorId =
        Guid.Parse("22222222-2222-2222-2222-222222222222");

    [Fact]
    public async Task BookAsync_ValidBooking_CreatesAppointmentAndReference()
    {
        var repository = new Mock<IAppointmentRepository>();

        repository
            .Setup(x => x.SlotAlreadyBookedAsync(10, It.IsAny<CancellationToken>()))
            .ReturnsAsync(false);

        Appointment? savedAppointment = null;

        repository
            .Setup(x => x.AddAsync(
                It.IsAny<Appointment>(),
                It.IsAny<CancellationToken>()))
            .Callback<Appointment, CancellationToken>((appointment, _) =>
            {
                savedAppointment = appointment;
                appointment.Id = 1;
            })
            .Returns(Task.CompletedTask);

        repository
            .Setup(x => x.SaveChangesAsync(It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask);

        var service = CreateService(
            repository.Object,
            DoctorResponse(),
            new DateTime(2026, 10, 6, 12, 0, 0, DateTimeKind.Utc));

        var request = new BookAppointmentRequestDto
        {
            DoctorId = DoctorId,
            SlotId = 10
        };

        var result = await service.BookAsync(PatientId, request);

        Assert.NotNull(savedAppointment);
        Assert.Equal(PatientId, savedAppointment!.PatientId);
        Assert.Equal(DoctorId, savedAppointment.DoctorId);
        Assert.Equal("Dr Test Doctor", savedAppointment.DoctorName);
        Assert.Equal(10, savedAppointment.DoctorAvailabilitySlotId);
        Assert.Equal(AppointmentStatus.Booked, savedAppointment.Status);

        Assert.False(string.IsNullOrWhiteSpace(result.AppointmentReference));
        Assert.StartsWith("CN-APT-", result.AppointmentReference);
        Assert.Equal("Booked", result.Status);
        Assert.Equal(10, result.SlotId);
    }

    [Fact]
    public async Task BookAsync_SlotNotReturnedByDoctorService_ThrowsSlotUnavailable()
    {
        var repository = new Mock<IAppointmentRepository>();

        var doctor = DoctorResponse();
        doctor.UpcomingSlots.Clear();

        var service = CreateService(
            repository.Object,
            doctor,
            new DateTime(2026, 10, 6, 12, 0, 0, DateTimeKind.Utc));

        var request = new BookAppointmentRequestDto
        {
            DoctorId = DoctorId,
            SlotId = 10
        };

        await Assert.ThrowsAsync<SlotUnavailableException>(
            () => service.BookAsync(PatientId, request));
    }

    [Fact]
    public async Task BookAsync_AlreadyBookedSlot_ThrowsDuplicateBooking()
    {
        var repository = new Mock<IAppointmentRepository>();

        repository
            .Setup(x => x.SlotAlreadyBookedAsync(10, It.IsAny<CancellationToken>()))
            .ReturnsAsync(true);

        var service = CreateService(
            repository.Object,
            DoctorResponse(),
            new DateTime(2026, 10, 6, 12, 0, 0, DateTimeKind.Utc));

        var request = new BookAppointmentRequestDto
        {
            DoctorId = DoctorId,
            SlotId = 10
        };

        await Assert.ThrowsAsync<DuplicateBookingException>(
            () => service.BookAsync(PatientId, request));

        repository.Verify(
            x => x.AddAsync(
                It.IsAny<Appointment>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task BookAsync_EmptyPatientId_ThrowsArgumentException()
    {
        var repository = new Mock<IAppointmentRepository>();

        var service = CreateService(
            repository.Object,
            DoctorResponse(),
            new DateTime(2026, 10, 6, 12, 0, 0, DateTimeKind.Utc));

        var request = new BookAppointmentRequestDto
        {
            DoctorId = DoctorId,
            SlotId = 10
        };

        await Assert.ThrowsAsync<ArgumentException>(
            () => service.BookAsync(Guid.Empty, request));
    }

    [Fact]
    public async Task BookAsync_PastSlot_ThrowsSlotUnavailable()
    {
        var repository = new Mock<IAppointmentRepository>();

        var doctor = DoctorResponse();

        doctor.UpcomingSlots[0].StartUtc =
            new DateTime(2026, 10, 6, 10, 0, 0, DateTimeKind.Utc);

        doctor.UpcomingSlots[0].EndUtc =
            new DateTime(2026, 10, 6, 10, 30, 0, DateTimeKind.Utc);

        var service = CreateService(
            repository.Object,
            doctor,
            new DateTime(2026, 10, 6, 12, 0, 0, DateTimeKind.Utc));

        var request = new BookAppointmentRequestDto
        {
            DoctorId = DoctorId,
            SlotId = 10
        };

        await Assert.ThrowsAsync<SlotUnavailableException>(
            () => service.BookAsync(PatientId, request));
    }

    private static AppointmentBookingService CreateService(
        IAppointmentRepository repository,
        DoctorProfileResponse doctorResponse,
        DateTime nowUtc)
    {
        var json = System.Text.Json.JsonSerializer.Serialize(
            doctorResponse,
            new System.Text.Json.JsonSerializerOptions
            {
                PropertyNamingPolicy =
                    System.Text.Json.JsonNamingPolicy.CamelCase
            });

        var handler = new FakeHttpMessageHandler(
            new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(
                    json,
                    Encoding.UTF8,
                    "application/json")
            });

        var httpClient = new HttpClient(handler)
        {
            BaseAddress = new Uri("https://doctor-payment.test/")
        };

        var contextAccessor = new HttpContextAccessor
        {
            HttpContext = new DefaultHttpContext()
        };

        var doctorPaymentClient =
            new DoctorPaymentClient(httpClient, contextAccessor);

        var timeProvider = new TestTimeProvider(nowUtc);

        return new AppointmentBookingService(
            repository,
            doctorPaymentClient,
            timeProvider);
    }

    private static DoctorProfileResponse DoctorResponse()
    {
        return new DoctorProfileResponse
        {
            DoctorId = DoctorId,
            FullName = "Dr Test Doctor",
            Availability = new DoctorAvailabilityResponse
            {
                HasAvailableSlots = true,
                AvailableSlotCount = 1,
                NextAvailableSlotUtc =
                    new DateTime(
                        2026, 10, 7, 9, 0, 0,
                        DateTimeKind.Utc)
            },
            UpcomingSlots =
            [
                new DoctorSlotResponse
                {
                    Id = 10,
                    StartUtc =
                        new DateTime(
                            2026, 10, 7, 9, 0, 0,
                            DateTimeKind.Utc),
                    EndUtc =
                        new DateTime(
                            2026, 10, 7, 9, 30, 0,
                            DateTimeKind.Utc)
                }
            ]
        };
    }

    private sealed class FakeHttpMessageHandler
        : HttpMessageHandler
    {
        private readonly HttpResponseMessage _response;

        public FakeHttpMessageHandler(HttpResponseMessage response)
        {
            _response = response;
        }

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            return Task.FromResult(_response);
        }
    }

    private sealed class TestTimeProvider : TimeProvider
    {
        private readonly DateTimeOffset _utcNow;

        public TestTimeProvider(DateTime utcNow)
        {
            _utcNow = new DateTimeOffset(utcNow);
        }

        public override DateTimeOffset GetUtcNow() => _utcNow;
    }
}