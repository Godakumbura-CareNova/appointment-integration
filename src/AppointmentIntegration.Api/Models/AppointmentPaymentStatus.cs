namespace AppointmentIntegration.Api.Models;

public enum AppointmentPaymentStatus
{
    Pending = 1,
    AwaitingBankTransferReceipt = 2,
    ReceiptUnderVerification = 3,
    AwaitingGatewayPayment = 4,
    Successful = 5,
    Failed = 6
}