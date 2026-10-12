# GCN-48 Appointment Cancellation: JMeter suite

**Functional and latency smoke test.** Exactly **5 scenarios, 5 HTTP requests, 1 request per scenario, 1 thread, 1 iteration**. It is **not** a concurrency, load or performance test.

| ID | Request | Token | Expected |
|----|---------|-------|----------|
| JM-01 | `GET /api/patient/appointments/48001/cancellation` (own unpaid cash appointment) | Patient 1 | 200, `allowed` true, `Unpaid`, no refund, a valid 64-hex `version` equal to the one computed offline |
| JM-02 | `GET /api/patient/appointments/48002/cancellation` (cash already paid) | Patient 1 | 200, `allowed` false, `CashAlreadyPaid`, version equal to the offline value |
| JM-03 | `GET /api/patient/appointments/48101/cancellation` (belongs to Patient 2) | Patient 1 | 404, body exactly `{"message":"Appointment not found."}`, nothing about the appointment disclosed |
| JM-04 | `GET /api/patient/appointments/48001/cancellation` | **Doctor** role | 403, empty body |
| JM-05 | `POST /api/patient/appointments/48005/cancellation` `{"expectedVersion":"<offline>","acknowledgeNoRefund":false,"reason":"GCN-48 JMeter synthetic QA cancellation"}` (verified bank transfer, 72 h before the start) | Patient 1 | 200, `Cancelled`, refund `Eligible` 1500, `PendingManualProcessing`; then read-only SQL checks the cancellation row, the manual-refund row and that nothing else changed |

## Recorded run
The suite was executed once against the isolated environment: 5 of 5 scenarios passed, 11 of 11 post-run database checks and 3 of 3 request-log checks. Results, limits and observations are in `GCN-48-QA-Findings.md`. The raw results, logs and fixtures are generated locally and are not committed.

## How JM-05's `expectedVersion` is computed and verified (before any request)
The version is `SHA256(JSON({snapshot, decision}))` of the appointment/payment state. `gcn48_version.py` ports the decision rules and the `System.Text.Json` serialisation and computes it from the fixtures. `gcn48_check_version.py` then builds `oracle/VersionOracle` (in a temporary folder outside every repository) against the **published backend build** and compares decision and version with the **real** `AppointmentCancellationPolicy` / `AppointmentCancellationService.Version` code for 239 snapshots and for all 8 fixtures. After seeding, `gcn48-check-version.sh --db` also has the real service read the seeded rows (SELECT only) and requires the same versions. JM-01 and JM-02 additionally assert version equality against the live server. Versions are never printed.

## Safety controls
- Isolated database `carenova_appointment_gcn48_qa`, limited user `gcn48_qa`, backend port **5248**, JMeter stop port **4548**. The guards refuse GCN-45/46/47 and shared names, and ports 3000, 5133-5137, 5199, 5235-5237, 5246, 5247 are protected.
- Secrets (JWT secret, DB password) live only in a mode-600 file in a mode-700 folder outside every git work tree; never printed. The MySQL root password is typed silently by you and never stored.
- Tokens are minted locally inside each sampler's pre-processor from the environment secret. There is **no JSR223 sampler**, no setup/authentication/health-check/teardown request, `httpclient4.retrycount=0`, redirects off. Readiness is checked with `lsof`.
- "Exactly five requests" is proven independently: the backend's own log must show exactly 5 "Request starting" lines, in order, answered 200, 200, 404, 403, 200.
- Post-run SQL (SELECT-only guard): exactly one cancellation row and one refund row (`PendingManualProcessing`, LKR, 1500.00), timestamps equal to the microsecond across the cancellation row, the appointment's `UpdatedAtUtc` and the response; the other 7 appointments and all 7 payments identical to the seed; no doctor-audit or reconciliation rows.
- Seeds are INSERT-only; the database must be empty to seed, so **each run needs a new empty database**. Fixtures are valid 36 hours.
- No production code is modified; nothing is committed or pushed.

## Coverage limitations (not claimed as covered)
- No concurrency, load or performance coverage. Five sequential requests prove nothing about throughput, contention or races (the backend's MySQL `FOR UPDATE` lock is exercised once, in the happy path only). The 3000 ms assertion is a sanity cap.
- JM-03 is one cross-patient read: no repeat, no unknown-id comparison, no cross-patient POST.
- JM-04 covers only the Doctor role (403). No-token 401, Admin, PharmacyStaff and invalid/expired tokens are not covered.
- JM-05 covers the verified bank-transfer refund-eligible happy path only: no stale-version 409, no idempotent repeat, no no-refund acknowledgement (400), no restricted-payment POST, no late-gateway-payment or concurrent cancellation race, no receipt/checkout interplay. The backend xUnit tests cover those.
- Only one cancellation is created per database.

## Order of use (every step needs your explicit approval)
1. `gcn48-make-test-secrets.sh` (secrets outside the repo)
2. `gcn48-create-database.sh --yes` (you type the MySQL root password)
3. `gcn48-preview-migrations.sh`, then `gcn48-apply-migrations.sh --yes` (6 migrations, 9 tables including the history table)
4. `gcn48-seed-fixtures.sh --yes`
5. `start-gcn48-env.sh --yes` (publishes and starts the backend on 5248; lsof readiness only)
6. `gcn48-preflight.sh` (secrets, isolation, seeded state, process identity, plan structure, **version check against the real service reading the seeded rows**)
7. `run-gcn48-jmeter.sh` (plan only), then `run-gcn48-jmeter.sh --yes`: pre-flight, one JMeter run, post-run SQL, request-log check, summary CSV
8. `stop-gcn48-env.sh`

Offline checks (no services, no secrets): `validate-gcn48-helpers.sh [--api-dir PUBLISHED_BUILD]`, `gcn48-check-assertions.sh`, `gcn48_verifier_selftest.py`, `gcn48-check-version.sh API_DIR`.
Regenerate the plan with `gen_gcn48_jmx.py`; never save it from the JMeter GUI, and never run it from the GUI against a live backend (no secret, extra requests).
