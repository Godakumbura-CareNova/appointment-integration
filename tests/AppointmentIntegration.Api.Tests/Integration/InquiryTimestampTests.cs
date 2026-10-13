using AppointmentIntegration.Api.Data;
using AppointmentIntegration.Api.Models;
using Microsoft.EntityFrameworkCore;

namespace AppointmentIntegration.Api.Tests.Integration;

public class InquiryTimestampTests
{
    [Theory]
    [InlineData(nameof(ContactInquiry.SubmittedAtUtc))]
    [InlineData(nameof(ContactInquiry.ReviewedAtUtc))]
    public void DatabaseTimestampsAreReadAsUtc(string propertyName)
    {
        using var db = new AppDbContext(new DbContextOptionsBuilder<AppDbContext>()
            .UseMySql("Server=localhost;Database=test;User=test;Password=test", new MySqlServerVersion(new Version(8, 0, 0))).Options);
        var property = db.Model.FindEntityType(typeof(ContactInquiry))!.FindProperty(propertyName)!;
        var converter = property.GetValueConverter();
        Assert.NotNull(converter);
        var stored = new DateTime(2026, 10, 8, 12, 0, 0, DateTimeKind.Unspecified);
        var restored = Assert.IsType<DateTime>(converter.ConvertFromProvider(stored));
        Assert.Equal(DateTimeKind.Utc, restored.Kind);
        Assert.Equal(stored.Ticks, restored.Ticks);
    }
}
