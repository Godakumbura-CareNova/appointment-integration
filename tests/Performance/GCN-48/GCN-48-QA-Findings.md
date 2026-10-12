# GCN-48 Appointment Cancellation: QA findings

Branch `feature/GCN-48-appointment-cancellation`. Scope: patient cancellation (`GET`/`POST api/patient/appointments/{id}/cancellation`), refund eligibility and manual-refund records.

## What was verified, and from which evidence
| Area | Result | Evidence |
|------|--------|----------|
| Selenium (frontend, `GCN48AppointmentCancellationSeleniumTests.cs`) | **5 passed, 0 failed, 0 skipped**, in two consecutive runs. Four deliberate faults (cash-paid made cancellable, conflict detection off, no-refund acknowledgement off, wrong refund status) each made exactly the intended test fail. | NUnit result files (`.trx`) and console output of both runs, kept outside the repositories |
| JMeter (this folder) | **5 of 5 scenarios passed**; **11 of 11** post-run database/refund-record checks; **3 of 3** server request-log checks; exactly 5 HTTP requests (4 GET, 1 POST) answered 200, 200, 404, 403, 200 | `results/run/summary.txt`, `results.jtl`, `verify-post.txt`, `verify-requests.txt` and the backend request log, kept outside the repositories (generated, git-ignored) |
| Backend xUnit (`AppointmentCancellation*Tests`) | **Not verified in this report.** The test files exist (policy, integration, persistence and concurrency tests) and were reviewed, but no GCN-48 result file was available to this report, so no pass/fail count is claimed here. The QA engineer reported 18 selected tests; attach the result file to confirm. | none available |
| Frontend Vitest (`PatientAppointmentCancellation.test.jsx`, `appointmentCancellationService.test.js`, payment page tests) | **Not verified in this report.** Same situation; the QA engineer reported 5 selected tests; no result file was available, so no count is claimed here. | none available |

## JMeter run (functional and latency smoke test)
| ID | Request | Result |
|----|---------|--------|
| JM-01 | GET eligibility, own unpaid appointment | 200, allowed, `Unpaid`, version equal to the offline value |
| JM-02 | GET eligibility, cash already paid | 200, not allowed, `CashAlreadyPaid` |
| JM-03 | GET another patient's appointment | 404, only the generic message |
| JM-04 | GET with a Doctor-role token | 403, empty body |
| JM-05 | POST cancellation, verified bank transfer, 72 h before the start | 200, Cancelled, refund Eligible 1500, `PendingManualProcessing` |

After JM-05, read-only SQL confirmed exactly one cancellation row and one refund row (`PendingManualProcessing`, LKR 1500.00), `CancelledAtUtc` equal to the appointment's `UpdatedAtUtc` and to the response timestamp (to the microsecond), and all other appointments and payments unchanged.
JM-05's `expectedVersion` was computed offline and checked against the real backend code (239 snapshots, all 8 fixtures) and against the real service reading the seeded rows before the run.
The first request (JM-01, about 1.5 s) includes server warm-up; the response times are a sanity record, not a performance claim.

## Limitations (not claimed as covered)
- **Not a concurrency, load or performance test.** One request per scenario proves behaviour for one input each.
- JM-03 is a single cross-patient read. JM-04 covers only the Doctor role (no-token 401, Admin, PharmacyStaff, invalid or expired tokens are not covered).
- JM-05 is the refund-eligible happy path only: no stale-version 409, no idempotent repeat, no no-refund acknowledgement (400), no restricted-payment POST, no late gateway payment, no concurrent cancellation/payment race (the MySQL row lock is exercised once, uncontended).
- Selenium tests use a mocked API: they prove what the browser shows and sends, not that the real server applies the payment rules, the 6-hour boundary, ownership or locking. Those belong to the backend tests.
- Each JMeter run changes one row, so it needs a new empty database; fixtures are valid for 36 hours.

## Observations and identified issues
1. **UI wording:** the success view says "Awaiting manual processing by pharmacy staff". The literal status `PendingManualProcessing` is validated by the frontend service but never shown to the patient. Not a defect if intended; the Selenium test asserts the wording and the accepted API value.
2. **Error shapes differ (code reading, not exercised end to end):** business-rule errors return `{ "message": ... }`, while model-validation errors (for example an expected version that is not 64 characters) return the framework's problem-details body. Clients and assertions must accept both.
3. **Migration is not atomic on MySQL (code and SQL reading):** MySQL commits DDL immediately, so the `START TRANSACTION` blocks in the generated migration script cannot roll back a half-applied run.
4. **`dotnet ef` dependency-injection message:** when no connection string is configured the tool prints that it could not build the application services and falls back to the design-time factory. The generated script is complete and identical to a verified preview; it does not affect the running application.
5. A cancelled appointment keeps its slot reserved (by design: the slot-uniqueness filter no longer excludes Cancelled).
6. No functional defect was found by the Selenium or JMeter runs.
