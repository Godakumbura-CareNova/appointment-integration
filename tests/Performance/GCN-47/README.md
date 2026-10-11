# GCN-47 Doctor Appointments: JMeter suite

Exactly **5 scenarios, 5 HTTP requests, 1 request per scenario, 1 iteration**. This is a
functional/security/audit check run through JMeter. It is **not a load test**.

| ID | Request | Token | Expected |
|----|---------|-------|----------|
| JM-01 | `GET /api/doctor/appointments` | Doctor 1 | 200, strict contract, ordered list, statistics {0,3,2,6}, `contactsUnavailable` true, no Doctor 2 data |
| JM-02 | `GET /api/doctor/appointments/47001` | Doctor 1 | 200, exact 17-field DTO for the seeded row |
| JM-03 | `GET /api/doctor/appointments/47101` (owned by Doctor 2) | Doctor 1 | 404, body empty or the bare framework ProblemDetails; no foreign data leaked |
| JM-04 | `GET /api/doctor/appointments` | Patient role | 403, empty body |
| JM-05 | `PATCH /api/doctor/appointments/47002/status` `{"status":"Confirmed","expectedStatus":"Booked","expectedUpdatedAtUtc":null}` | Doctor 1 | 200 `{id,status,updatedAtUtc}`; then read-only SQL proves one audit row |

## Safety controls
- Dedicated DB `carenova_appointment_gcn47_qa`, limited user `gcn47_qa`, backend on port **5247**, JMeter stop port 4547. Scripts refuse GCN-45/46/49 names and ports (3000, 5133-5137, 5199, 5235-5237, 5246).
- Secrets (DB password, JWT secret) live only in a mode-600 file in a mode-700 folder outside every git work tree. The MySQL root password is typed silently by you and never stored.
- Test JWTs are minted locally inside each sampler's pre-processor. No JSR223 *sampler*, no setup/auth/health/teardown requests; readiness uses `lsof`, not HTTP.
- Retries 0 (`httpclient4.retrycount=0`), redirects off, 1 thread, 1 loop, ramp 0.
- Request count is proven independently: the backend's own log must show exactly 5 "Request starting" lines, in order, with statuses 200, 200, 404, 403, 200.
- JM-05 integrity: SQL (SELECT-only guard) checks exactly one `AppointmentStatusChanges` row (47002, Doctor 1, Booked to Confirmed), timestamps equal to the microsecond across audit row, appointment row and response, and every other appointment/payment unchanged.
- Seeds are INSERT-only; a database must be empty to seed, so **each run needs a new empty database**. Fixtures are valid 36 h.
- No production code is modified; nothing is committed or pushed.

## Coverage limitations (stated, not hidden)
- **No concurrency or load coverage.** Five sequential requests prove nothing about throughput, contention or race conditions. The 3000 ms DurationAssertion is a sanity cap, not a performance claim.
- **JM-03** is a single cross-doctor read. It does not test concurrent access, repeats, PATCH/modify on another doctor's row, or comparison with a non-existent id (to show enumeration resistance).
- **JM-04** covers only the Patient role, giving 403. Missing token (401), invalid/expired/wrong-issuer tokens, Admin and PharmacyStaff are not covered. Say if you want the 401 no-token case instead.
- No appointments dated "today" are seeded, so the time-dependent flags (`isToday`, same-day allowedStatuses) are only partly exercised.
- Patient contact enrichment is not covered: the user-auth service is absent, so `contactsUnavailable: true` with null names/phones is asserted.
- Stale-update (409), invalid-transition (400) and unknown-id (404) paths of PATCH are not covered; these belong to backend integration tests.

## Order of use (each step needs your explicit approval)
1. `gcn47-make-test-secrets.sh` (secrets outside the repo)
2. `gcn47-create-database.sh` (you type the MySQL root password)
3. `gcn47-preview-migrations.sh`, then `gcn47-apply-migrations.sh --yes` (5 migrations)
4. `gen_gcn47_fixtures.py`, then `gcn47-seed-fixtures.sh --yes`
5. `start-gcn47-env.sh` (backend on 5247)
6. `run-gcn47-jmeter.sh` (plan only) then `run-gcn47-jmeter.sh --yes`: pre-flight, one JMeter run, post-run SQL, request-log check, summary CSV
7. `stop-gcn47-env.sh`

`validate-gcn47-helpers.sh` is the static check (no services touched). Regenerate the plan with `gen_gcn47_jmx.py`; never save it from the JMeter GUI.

## Conventions
The DB name, DB user, port 5247 and stop port 4547 follow the GCN-46 convention. Results of the recorded run and its caveats are in `GCN-47-QA-Findings.md`.

## Rules for the plan file
Never save the plan from the JMeter GUI: a GUI save rewrites the file (embedding local paths and listener filenames). Regenerate it with `gen_gcn47_jmx.py`. Do not run the plan from the GUI against a live backend either: the GUI has no `GCN47_JWT_SECRET`, so tokens cannot be minted, and any extra request breaks the "exactly 5 requests" proof.
