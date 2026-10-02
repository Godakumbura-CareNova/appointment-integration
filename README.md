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
