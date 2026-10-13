# GCN-53 Admin Dashboard: JMeter suite (executed once; see GCN-53-QA-Findings.md)

**6 logical scenarios, 24 read-only GET samplers, 66 requests per run, one thread.** Functional, response-time and repeated-request consistency check. It is **not** a load, concurrency or capacity test.

Results and findings of the executed run (66-request suite and the six-request suite in `six/`): `GCN-53-QA-Findings.md`.

## What the backend actually offers (inspected, nothing invented)
All four endpoints are `[Authorize(Roles = "Admin")]` (JWT bearer; 401 without a valid token, 403 for another role):

| Endpoint | Behaviour |
|---|---|
| `GET /api/admin/dashboard/appointments` | total, status counts, today (Asia/Colombo day) and upcoming (Booked/Confirmed, start after now), the 5 newest appointments with payment method/status |
| `GET /api/admin/dashboard/appointment-payments` | payment totals and status counts, pending bank transfers (receipt under verification WITH a pending receipt), 5 newest dated confirmed payments, income today/month (Asia/Colombo), undated successful payments |
| `GET /api/admin/appointments?search&page&pageSize` | newest first, search by reference or doctor name, `pageSize` 1-100, `page` >= 1, otherwise 400 `{message}` |
| `GET /api/admin/reports/appointment-income?from&to` | successful payments confirmed in [from, to) and not after now, grouped by Asia/Colombo date; windows over 32 days give 400 `{message}` |

`AdminDashboardController` and `AdminDashboardDto` in this repository are **empty (0-byte) files**; the real routes are the four above. The user, doctor, medicine and fee-request admin endpoints belong to other services and are outside this suite.

## Scenarios (adjusted to the real API)
| ID | Requests | Expected |
|----|----------|----------|
| J01 Admin dashboard appointment summary | GET appointment summary, GET appointment-payment summary (Admin) | 200 x2: exact contract; totals, status counts and today/upcoming equal the independent oracle; the 5 newest appointments in order with payment details; pending transfers exclude a rejected receipt; income and recent payments equal the oracle |
| J02 Admin appointment listing | default page, page 2 size 5, doctor search, reference search page 2, `pageSize=101` | 200 x4 with items, order, totalCount, page, pageSize, totalPages equal the fixtures; 400 with exactly the documented message |
| J03 Admin appointment reports | 21-day window, 40-day window | 200: days grouped by Sri Lanka date (two confirmations seconds either side of Sri Lanka midnight on different dates), amounts and counts, undated count, future-dated payments excluded; 400 for the long window |
| J04 Unauthenticated access | the four endpoints without a token | 401 x4, empty body |
| J05 Non-admin access | Patient on all four, PharmacyStaff on summary and list, Doctor on payment summary and report | 403 x8, empty body |
| J06 Repeated dashboard requests | 15 x (summary + payment summary + list page 1 size 5) | 200 x45, values equal the oracle every time; average, median, p95 and max per request type and overall; mean <= 400 ms and p95 <= 750 ms, each request <= 1500 ms |

Thresholds are documented sanity limits for a local development machine (3000 ms per request for J01-J05), not service levels.

## Safety controls
- Isolated database `carenova_appointment_gcn53_qa`, limited user `gcn53_qa`, backend port **5253**, JMeter stop port **4553**. Guards refuse GCN-45/46/47/48/51 and shared names; ports 3000, 5133-5137, 5199, 5235-5237, 5246-5248 and 5251 are protected and never touched.
- Host and port are JMeter properties (`gcn53.host`, `gcn53.port`) but **guarded**: anything other than localhost/127.0.0.1 and 5253 makes the sampler target an unreachable `.invalid` address and fails the scenario.
- Secrets (JWT secret, DB password) only in a mode-600 file in a mode-700 folder outside every git work tree; never printed. The MySQL root password is typed by the user. No credentials in the plan: tokens are minted locally from the environment secret.
- **Read-only**: GET only. Read-only SQL proves every table is identical before and after the run; the backend's own log must show exactly the 66 expected requests, in order, with the expected statuses. Retries 0, redirects off.
- Generated files (fixtures, results, logs, evidence, migration preview) are written **outside the repository**, default `~/carenova/qa-reports/GCN-53/jmeter` (override with `GCN53_OUT_DIR`).
- Fixtures are synthetic and valid 72 hours; time-dependent figures (today, upcoming, income, daily totals) are recomputed by the assertions from the stored lists at the time the server reports.

## Coverage limitations (not claimed as covered)
- One thread, sequential: no concurrency, load or capacity claim; 66 requests in total.
- One synthetic data set; paging beyond 3 pages, the empty database and the reconciled-funds exclusion are covered by the backend xUnit tests, not here.
- Other admin endpoints (users, doctors, medicines, fee requests, medicine payments) belong to other services.

## Order of use (every step needs explicit approval)
1. `gcn53-make-test-secrets.sh`
2. `gcn53-create-database.sh --yes` (the user types the MySQL root password)
3. `gcn53-preview-migrations.sh` (offline), then `gcn53-apply-migrations.sh --yes` (8 migrations, 11 tables incl. the history table)
4. `gcn53-seed-fixtures.sh --yes`
5. `start-gcn53-env.sh --yes`, then `gcn53-preflight.sh`
6. `run-gcn53-jmeter.sh` (plan only), then `run-gcn53-jmeter.sh --yes`
7. `stop-gcn53-env.sh`

Offline checks (no services, no secrets): `validate-gcn53-helpers.sh`, `gcn53-check-assertions.sh`, `gcn53_verifier_selftest.py`.
Regenerate the plan with `gen_gcn53_jmx.py`; never save it from the JMeter GUI and never run it from the GUI against a live backend.
