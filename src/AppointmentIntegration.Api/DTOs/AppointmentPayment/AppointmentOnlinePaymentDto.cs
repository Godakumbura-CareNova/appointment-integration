namespace AppointmentIntegration.Api.DTOs.AppointmentPayment;

public class StartAppointmentOnlinePaymentDto
{
    public string? FirstName { get; set; }

    public string? LastName { get; set; }

    public string? Email { get; set; }

    public string? Phone { get; set; }

    public string? Address { get; set; }

    public string? City { get; set; }
}

public class AppointmentOnlinePaymentSessionDto
{
    public int AttemptId { get; set; }

    public int AttemptNumber { get; set; }

    public bool Sandbox { get; set; }

    public string MerchantId { get; set; } = string.Empty;

    public string GatewayOrderId { get; set; } = string.Empty;

    public string Items { get; set; } = string.Empty;

    public string Amount { get; set; } = string.Empty;

    public string Currency { get; set; } = string.Empty;

    public string Hash { get; set; } = string.Empty;

    public string NotifyUrl { get; set; } = string.Empty;

    public string ReturnUrl { get; set; } = string.Empty;

    public string CancelUrl { get; set; } = string.Empty;

    public string FirstName { get; set; } = string.Empty;

    public string LastName { get; set; } = string.Empty;

    public string Email { get; set; } = string.Empty;

    public string Phone { get; set; } = string.Empty;

    public string Address { get; set; } = string.Empty;

    public string City { get; set; } = string.Empty;

    public string Country { get; set; } = string.Empty;

    public string Custom1 { get; set; } = string.Empty;

    public string AppointmentReference { get; set; } = string.Empty;
}

public class AppointmentOnlinePaymentResultDto
{
    public string Outcome { get; set; } = string.Empty;

    public string Message { get; set; } = string.Empty;

    public bool CanRetry { get; set; }

    public bool IsTest { get; set; }

    public string TransactionReference { get; set; } = string.Empty;

    public string? FailureCode { get; set; }

    public AppointmentPaymentResponseDto Payment { get; set; } = new();
}