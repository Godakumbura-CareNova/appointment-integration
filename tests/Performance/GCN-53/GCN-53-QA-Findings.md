# GCN-53 Admin Dashboard: JMeter QA findings

Branch `feature/GCN-53-admin-dashboard`, backend (appointment service) only. Two read-only JMeter suites were executed once each, on 2026-10-12, against the same isolated environment:
the **66-request suite** (`tests/Performance/GCN-53/`) and the **six-request suite** (`tests/Performance/GCN-53/six/`).

## 1. Test objectives and environment
**Objectives:** verify, through the HTTP API and with synthetic data, that the four GCN-53 admin endpoints return the documented contract and correct figures, paginate and group correctly, reject bad input, and enforce authorization; and that the dashboards answer repeated read-only requests consistently within sanity time limits.

| Endpoint (all `[Authorize(Roles = "Admin")]`) | Purpose |
|---|---|
| `GET /api/admin/dashboard/appointments` | totals, status counts, today / upcoming (Asia/Colombo), five newest appointments |
| `GET /api/admin/dashboard/appointment-payments` | payment counts, pending bank transfers, recent confirmed payments, income today / this month, undated payments |
| `GET /api/admin/appointments?search&page&pageSize` | paginated, searchable appointment list |
| `GET /api/admin/reports/appointment-income?from&to` | successful payments grouped by Sri Lanka date |

`AdminDashboardController` and `AdminDashboardDto` are empty (0-byte) files in this repository; the four routes above are the real API.

**Environment (isolated, local):** backend `localhost:5253` (published GCN-53 build, Staging), MySQL database `carenova_appointment_gcn53_qa` with limited user `gcn53_qa` (sees only its own database), 8 migrations (11 tables), JMeter 5.6.3 CLI on Java 21, one thread. **Synthetic fixtures:** 14 appointments, 11 payments (7 successful: dated, undated and future-dated; one bank transfer with a pending receipt, one with a rejected receipt), 2 receipts, 4 patients, no real data. Tokens are minted locally from a throw-away secret kept outside the repository; the plan contains no credential. The GCN-45/46/47/48/51 environments (including the GCN-51 backend on 5251) were not used or modified.

## 2. Original suite: 66 requests, 6 of 6 scenarios passed, 0 failed
24 GET samplers in 6 logical scenarios, one thread.

| ID | Scenario | Requests | Expected | Actual | avg / median / p95 / max (ms) | Result |
|----|----------|----------|----------|--------|-------------------------------|--------|
| J01 | Admin dashboard appointment summary | 2 | 200, 200 | 200 x2 | 311 / 311 / 564 / 564 | PASS |
| J02 | Admin appointment listing (default, page 2, doctor search, reference search page 2, `pageSize=101`) | 5 | 200 x4, 400 | 200 x4, 400 | 8 / 6 / 18 / 18 | PASS |
| J03 | Admin appointment income report (21-day window, 40-day window) | 2 | 200, 400 | 200, 400 | 9 / 9 / 17 / 17 | PASS |
| J04 | Unauthenticated access (four endpoints) | 4 | 401 x4 | 401 x4 | 1 / 0 / 4 / 4 | PASS |
| J05 | Non-admin access (Patient x4, PharmacyStaff x2, Doctor x2) | 8 | 403 x8 | 403 x8 | 1 / 0 / 5 / 5 | PASS |
| J06 | Repeated dashboard requests (15 x summary, payment summary, list) | 45 | 200 x45 | 200 x45 | 4 / 3 / 6 / 11 | PASS |

**Totals:** 66 requests: 52 x 200, 2 x 400 (the two deliberate invalid inputs), 4 x 401, 8 x 403; 0 failed samples; overall avg / median / p95 / max = 13 / 3 / 17 / 564 ms.
**J06 by request type (n = 15 each, avg / median / p95 / max ms):** appointment summary 4 / 3 / 11 / 11, payment summary 5 / 4 / 7 / 7, list 2 / 2 / 3 / 3. Documented limits were met: every request at most 1500 ms (max 11), mean at most 400 ms (4), p95 at most 750 ms (6). The 311 ms of J01 is the first request after start (server warm-up).

## 3. New suite: six test cases, exactly 6 requests, 6 of 6 passed
Six GET samplers (one per case), one thread, one iteration, no loops, no retries.

| ID | Test case | Request (token) | Expected | Actual | Response time | Result |
|----|-----------|-----------------|----------|--------|---------------|--------|
| T01 | Admin appointment summary | `GET /api/admin/dashboard/appointments` (Admin) | 200 | 200 | 77 ms | PASS |
| T02 | Admin payment summary and income | `GET /api/admin/dashboard/appointment-payments` (Admin) | 200 | 200 | 19 ms | PASS |
| T03 | Admin appointment listing and pagination | `GET /api/admin/appointments?page=2&pageSize=5` (Admin) | 200 | 200 | 9 ms | PASS |
| T04 | Admin income report and date grouping | `GET /api/admin/reports/appointment-income?from&to`, 21 days (Admin) | 200 | 200 | 9 ms | PASS |
| T05 | Unauthenticated access to financial data | `GET /api/admin/dashboard/appointment-payments` (no token) | 401 | 401 | 2 ms | PASS |
| T06 | Non-admin access to appointment data | `GET /api/admin/appointments` (Patient) | 403 | 403 | 2 ms | PASS |

6 requests: 4 x 200, 1 x 401, 1 x 403; 0 failed samples. Each time is a single sample; no average, median or percentile is claimed for this suite. The assertion scripts are byte-identical to the validated ones of the 66-request suite.

## 4. What the assertions verified
- **Contract and figures:** exact field sets; totals and status counts equal the fixtures and add up; today / upcoming, income today / this month and the daily report totals are recomputed by an independent oracle at the time the server reports (Asia/Colombo calendar day and month); the five newest items are newest first; pagination (`totalCount`, `page`, `pageSize`, `totalPages`) equals the fixtures.
- **Business rules:** the pending transfer is listed and the one with a rejected receipt is excluded; future-dated and undated successful payments are excluded from recent payments and daily totals, and undated ones are counted separately; the two confirmations seconds either side of Sri Lanka midnight fall on different dates; the 40-day window and `pageSize=101` are rejected with exactly the documented messages and no stack trace.
- **Authorization:** no token gives 401, a valid Patient, PharmacyStaff or Doctor token gives 403, and every denied response has an empty body with no appointment or payment data.

## 5. Database integrity and request proof (both suites)
| Check | 66-request suite | Six-request suite |
|---|---|---|
| Pre-run: database equals the seed (counts, every appointment, payment and receipt), fixtures fresh | 6 of 6 PASS | 6 of 6 PASS |
| Post-run: every table and row identical to the pre-run snapshot (nothing created, changed or deleted) | 5 of 5 PASS | 5 of 5 PASS |
| Backend's own request log: exactly the expected GET requests, in order, with the expected statuses | 66 requests, 3 of 3 PASS | 6 requests (200, 200, 200, 200, 401, 403), 3 of 3 PASS |
| Pre-flight (no HTTP): secrets mode 600, limited user isolation, process identity, plan structure | PASS | PASS (12 of 12) |

## 6. Coverage limitations
- **Functional response-time smoke testing, not load testing.** Both suites use one thread and sequential requests (66 and 6 in total). There is no concurrency, load, capacity or stress claim, and the response-time limits (3000 ms per request, and 1500 ms / mean 400 ms / p95 750 ms for J06) are sanity limits for a local development machine, not service levels.
- The six-request suite is a deliberate subset: it does not cover search, the 400 cases, the other non-admin roles, the 401 on the list and report endpoints, or repeated requests; the 66-request suite covers those.
- One synthetic data set; paging beyond three pages, the empty database and the exclusion of reconciled funds from income are covered by the backend xUnit tests, not by JMeter.
- The admin endpoints of other services (users, doctors, medicines, fee requests, medicine payments) are outside this backend and outside these suites.
- The xUnit, Vitest and Selenium results for GCN-53 are not part of this report.

## 7. Application defects
**None identified by these JMeter suites.** Observations, not defects:
1. `AdminDashboardController` and `AdminDashboardDto` are empty files; the real routes are on other controllers. They could be removed or filled.
2. `dotnet ef` needs a connection string to generate a migration script (the application registers its database context even without one), so the suite supplies an obviously dummy value for that one offline command; no connection is opened.

## 8. Supporting evidence (kept outside the repository, generated and git-ignored)
| Evidence | Path |
|---|---|
| 66-request results, summary, JTL, console and JMeter logs | `~/carenova/qa-reports/GCN-53/jmeter/results/run/` (`summary.txt`, `results.jtl`) and `results/GCN-53-JMeter-results.csv` |
| 66-request verifications (pre / post / request log) and pre-flight | `~/carenova/qa-reports/GCN-53/jmeter/evidence/` |
| Six-request results, report, JTL and CSV | `~/carenova/qa-reports/GCN-53/jmeter-six/results/run/` and `results/GCN-53-six-results.csv` |
| Six-request verifications and pre-flight | `~/carenova/qa-reports/GCN-53/jmeter-six/evidence/` |
| Backend request log (shared by both runs) and setup logs | `~/carenova/qa-reports/GCN-53/jmeter/logs/` |
| Seeded fixtures (synthetic) | `~/carenova/qa-reports/GCN-53/jmeter/fixtures/` |

How to re-run: see `README.md` and `six/README.md` (offline validators `validate-gcn53-helpers.sh` and `six/validate-gcn53-six.sh`).
