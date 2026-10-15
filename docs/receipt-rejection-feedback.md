# Patient appointment receipt rejection feedback

The payment still returns to `AwaitingBankTransferReceipt` after rejection so the patient can submit another receipt. No payment lifecycle or verification rule changes.

Patient appointment list/details and payment details now include optional `latestReceipt` metadata: `status`, `rejectionReason`, and `reviewedAtUtc`. Metadata is restricted to the owning patient. A corrected upload returns the newest pending receipt instead of the previous rejection.

Rejected receipts also serve as persistent patient bell notifications. Receipt IDs identify notifications, so retrying a completed staff review cannot create duplicates. Historical rejection notifications remain available after a corrected upload; their message directs the patient to the latest status rather than asking for another upload.

## Database update required before backend rollout

Migration: `20261015071737_PatientReceiptRejectionNotificationRead`.

It adds one nullable `datetime(6)` column, `PatientNotificationReadAtUtc`, to `AppointmentReceipts`. It does not change existing receipt data or payment statuses. Previously rejected receipts are initially unread.

From the appointment-integration repository, with the intended database connection configured:

```powershell
dotnet ef database update --project src/AppointmentIntegration.Api
```

Apply the migration before restarting/deploying the updated backend, then deploy the frontend. Migration generation and tests do not update the application's database automatically.

## Notification endpoints

All endpoints require the authenticated `Patient` or `User` role and use the patient's token identity, never a caller-supplied patient ID.

- `GET /api/patient/appointment-notifications`: unread rejected receipts plus the most recent 50 read rejection notifications.
- `POST /api/patient/appointment-notifications/{receiptId}/read`: mark one owned rejection notification read; repeating it is safe.
- `POST /api/patient/appointment-notifications/read-all`: mark this patient's unread rejection notifications read.

The existing notification bell loads these alongside medicine/order notifications and refreshes when opened. Clicking a notification opens and reloads the relevant appointment payment page. There is no new push or email service.
