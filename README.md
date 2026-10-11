# appointment-integration
Manages doctors, doctor availability, appointments, consultation fees, and appointment-related integration for CareNova.

## Sprint 4 service structure (GCN-44 to GCN-53)

.NET 8 Web API in `src/AppointmentIntegration.Api`, tests in `tests/AppointmentIntegration.Api.Tests`.
Placeholder files mark where each story's work goes; the code is left to the Sprint 4 developers.

| Story | Area |
| --- | --- |
| GCN-44 | Appointment booking and time slot selection |
| GCN-45 | Appointment payment (cash, bank transfer, PayHere) |
| GCN-46 | Patient appointment list and details |
| GCN-47 | Doctor appointment management |
| GCN-48 | Cancellation and refund rules |
| GCN-49 / GCN-50 | Public home, about and contact content |
| GCN-51 to GCN-53 | Patient, pharmacy staff, doctor and admin dashboard data |

- Local URL: `http://localhost:5136` (container listens on `8080`).
- Secrets (`ConnectionStrings__DefaultConnection`, `JwtSettings__Secret`, `PayHere__MerchantSecret`) go in user secrets or Azure app settings, never in git.
- CI (`.github/workflows/ci.yml`) restores, builds, tests and builds the Docker image on `main`, `develop` and `feature/**`.
- CD (`.github/workflows/cd.yml`) is run manually and needs the `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `AZURE_APPOINTMENT_APP_NAME` and `AZURE_APPOINTMENT_PUBLISH_PROFILE` repository secrets.

## GCN-47 doctor appointments

Doctor-only routes: GET `/api/doctor/appointments`, GET `/api/doctor/appointments/{id}`, PATCH `/api/doctor/appointments/{id}/status`. Identity comes from the validated JWT; foreign appointments return 404. The collection includes Sri Lanka calendar memberships, current payment details and unique patient counts. Status updates use expected status/update timestamp, enforce consultation-time rules and save an audit row atomically. No Show is a terminal appointment status.

Configure `UserAuthService__BaseUrl` as the **direct auth service origin** (locally `http://localhost:5133`). Auth must configure `AppointmentIntegration__BaseUrl` pointing back to this service, using compatible JWT issuer/audience/signing settings. Contact lookups expose only assigned patients' names/mobile numbers and fail safely without hiding appointment records. POST `/api/doctor/appointments/patient-access` is the doctor-only, database-only ownership check used by auth; it never invokes contact lookup.

Apply `20261011035248_GCN47DoctorAppointmentStatusHistory` before enabling updates. The migration adds only `AppointmentStatusChanges`; existing booking/payment tables remain intact. **The design-time DbContext factory has a dummy connection**, so explicitly pass the intended connection when applying migrations:

```powershell
# Configure this environment variable privately for the intended database first.
dotnet ef database update --project src/AppointmentIntegration.Api --configuration Release --connection $env:ConnectionStrings__DefaultConnection
```

Do not commit connection strings or tokens. Tests use isolated SQLite/InMemory databases; run `dotnet test AppointmentIntegration.sln --configuration Release`.
