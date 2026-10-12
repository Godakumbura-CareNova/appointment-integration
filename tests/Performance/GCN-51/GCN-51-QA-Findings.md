# GCN-51 Role Dashboards: JMeter QA findings

Branch `feature/GCN-51-role-dashboards`. Scope: the appointment-service dashboard APIs: `GET /api/patient/dashboard/appointments`, `GET /api/staff/dashboard/appointment-payments`, and the doctor appointments endpoint the doctor dashboard reads.

## What was verified, and from which evidence
| Area | Result | Evidence |
|------|--------|----------|
| JMeter (this folder) | **9 of 9 scenarios passed**; exactly 9 HTTP samplers (one per scenario), 38 requests (J09 loops its sampler 30 times): 35 x 200, 1 x 401, 2 x 403; 0 errors | `results/run/summary.txt`, `results.jtl` (kept outside the repositories, generated, git-ignored) |
| Database integrity | **5 of 5** read-only checks: every table identical before and after the run (the suite only reads) | `evidence/verify-post.json` |
| Server request log | **3 of 3** checks: exactly the 38 expected GET requests, in order, with the expected statuses; no health check, retry, redirect or write | `evidence/verify-requests.json` |
| Pre-run state | 6 of 6 checks: database seeded exactly as the fixtures | `evidence/verify-pre.json` |
| Backend xUnit, Vitest, Selenium | Reported by the QA engineer as 28/28, 6/6 and 5/5 for GCN-51. **Not verified in this report** (no result files were available to it) | none available |

## Scenarios
| ID | Request | Result |
|----|---------|--------|
| J01 | GET patient dashboard (Patient) | 200, full documented contract |
| J02 | GET patient dashboard (Patient) | 200, count 7, first five rows in order, payment-status counts equal the fixtures |
| J03 | GET staff payments dashboard (PharmacyStaff) | 200, full documented contract |
| J04 | GET staff payments dashboard (PharmacyStaff) | 200, 6 pending transfers (5 shown), 5 newest dated payments, income equal to an independent oracle for Asia/Colombo |
| J05 | GET doctor appointments (Doctor) | 200, statistics and ordered list equal the fixtures |
| J06 | GET staff payments dashboard, no token | 401, empty body |
| J07 | GET staff payments dashboard (Patient) | 403, empty body |
| J08 | GET patient dashboard (PharmacyStaff) | 403, empty body |
| J09 | GET staff payments dashboard, one sampler looped 30 times | 30 x 200, values stable; mean 5 ms (limit 400), p95 7 ms (limit 750), max 8 ms (limit 1500) |

The first request (J01, 549 ms) includes server warm-up. The thresholds are sanity limits for a local development machine, not service levels.

## Replacement and trade-offs (documented, nothing weakened)
- **J05 is a replacement.** The backend has no doctor dashboard endpoint (`DoctorDashboardController` and the other role dashboard controllers are empty files); the doctor dashboard reads `GET /api/doctor/appointments`.
- With exactly one sampler per scenario, J06 covers the unauthenticated request on the staff dashboard only, and J09 repeats only the staff dashboard. The patient dashboard's 401 is covered by the backend xUnit tests.

## Limitations (not claimed as covered)
- One thread, sequential requests: no concurrency, load or capacity claim.
- One patient's and one staff member's view. Admin, the `User` role alias, expired or invalid tokens, empty-state dashboards and the exclusion of reconciled funds from income are covered by backend tests, not here.
- The medicine-order and medicine-payment dashboards belong to other services and are not covered; patient contact enrichment is absent (J05 asserts contacts are reported unavailable).
- The suite is read-only and repeatable, but seeding needs a new empty database.

## Observations
1. `Program.cs` registers the database context even when no connection string is configured, so `dotnet ef` fails with "connectionString cannot be empty" unless a connection string is supplied. The suite passes an obviously dummy value for that one offline command (no connection is opened). The application would also fail only at first database use rather than at startup.
2. The branch carries the GCN-50 public-information migration, so the schema has 11 tables including the history table.
3. No application defect was found by the JMeter run.
