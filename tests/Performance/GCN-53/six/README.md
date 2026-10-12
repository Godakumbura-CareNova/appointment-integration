# GCN-53 Admin Dashboard: six-request JMeter suite

**Exactly 6 test cases, 6 HTTP GET samplers (one per case), one thread, one iteration, 6 requests in total.** No loops, no retries, no setup/health-check/teardown requests. A functional smoke test of the six most important admin dashboard behaviors; **not** a load, concurrency, stability or response-time-statistics test (one sample per case). The 66-request suite in `..` is unchanged and remains the broader suite.

| ID | Request | Token | Expected |
|----|---------|-------|----------|
| T01 | `GET /api/admin/dashboard/appointments` | Admin | 200; exact contract; totals and status counts equal the fixtures; today/upcoming recomputed for Asia/Colombo; five newest appointments newest first with payment details |
| T02 | `GET /api/admin/dashboard/appointment-payments` | Admin | 200; counts; pending transfer included and the rejected-receipt one excluded; recent payments newest confirmation first (future-dated and undated excluded); income today/month and undated payments equal the oracle |
| T03 | `GET /api/admin/appointments?page=2&pageSize=5` | Admin | 200; items 6-10 newest first with payment details; totalCount 14, page 2, pageSize 5, totalPages 3 |
| T04 | `GET /api/admin/reports/appointment-income?from&to` (21 days) | Admin | 200; days grouped by Sri Lanka date (two confirmations seconds either side of midnight on different dates), amounts and counts equal the oracle, undated counted separately, currency LKR |
| T05 | `GET /api/admin/dashboard/appointment-payments` | none | 401, empty body |
| T06 | `GET /api/admin/appointments` | Patient | 403, empty body |

Each case also asserts the JSON content type (200 cases) and a 3000 ms sanity cap (not a service level).

## Same safeguards as the 66-request suite
Isolated database `carenova_appointment_gcn53_qa`, backend port **5253**, JMeter stop port 4553; guarded host/port (only localhost:5253); locally minted tokens from the secrets file (no credentials in the plan); read-only GET requests; the assertion scripts are **byte-identical** to the validated ones of the 66-request plan (checked by the validator).

## How it is proven
- The backend's own log, counted from the baseline recorded by the pre-flight, must show **exactly 6 GET requests**, in order, answered **200, 200, 200, 200, 401, 403**.
- Read-only SQL before and after proves **every table and row is identical**.
- Results and evidence go to `~/carenova/qa-reports/GCN-53/jmeter-six/` (outside the repository). Its `fixtures` and `logs` folders are links to the shared seeded fixtures and backend log of `../jmeter`, which are only read.

## Use (needs the GCN-53 environment: secrets, database seeded, backend on 5253)
```
./validate-gcn53-six.sh          # offline checks
./gcn53-six-preflight.sh         # pre-flight, no HTTP
./run-gcn53-six.sh               # shows the plan
./run-gcn53-six.sh --yes         # pre-flight, one JMeter CLI run, database check, request check, report
```
Never save the plan from the JMeter GUI and never run it from the GUI against a live backend.
