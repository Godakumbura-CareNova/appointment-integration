# GCN-51 Role Dashboards: JMeter suite (prepared and validated offline; NOT yet executed)

**9 scenarios, exactly 9 read-only GET samplers (one per scenario), 38 requests per run (J09 loops its single sampler 30 times), one thread.** Functional, response-time and repeated-request stability check. It is **not** a load, concurrency or capacity test.

## What the backend actually offers (inspected, nothing invented)
| Endpoint | Authorization | Notes |
|---|---|---|
| `GET /api/patient/dashboard/appointments` | `Roles = "Patient,User"` | upcoming count (Booked/Confirmed, start after now), first 5 by (start, id), payment-status counts of ALL the patient's payments |
| `GET /api/staff/dashboard/appointment-payments` | policy `PharmacyStaff` (role `PharmacyStaff` only) | pending bank transfers (ReceiptUnderVerification **with** a PendingVerification receipt), 5 newest dated confirmed payments, income today/month in Asia/Colombo, undated successful payments, reconciled funds excluded |
| `GET /api/doctor/appointments` (GCN-47) | `Roles = "Doctor"` | what the **doctor dashboard** uses: statistics + list |

`DoctorDashboardController`, `PatientDashboardController`, `PharmacyStaffDashboardController`, `AdminDashboardController` and `DashboardService` are **empty (0-byte) files** in this repository. The medicine-order and medicine-payment dashboard endpoints belong to other services (pharmacy order, doctor payment) and are outside this suite.

## Scenarios
| ID | Request(s) | Token | Expected |
|----|------------|-------|----------|
| J01 | GET patient dashboard | Patient 1 | 200, JSON, full documented contract (fields, types, limit of 5, fresh UTC timestamps) |
| J02 | GET patient dashboard | Patient 1 | 200, upcoming count 7, the first five in (start, id) order with payment method/status, payment-status counts equal the fixtures, nothing of other patients |
| J03 | GET staff payments dashboard | PharmacyStaff | 200, JSON, full documented contract |
| J04 | GET staff payments dashboard | PharmacyStaff | 200, 6 pending transfers (5 shown, oldest update first, the rejected receipt excluded), 5 newest dated payments (future-dated and undated excluded), income recomputed independently for Asia/Colombo today / this month, undated reported separately |
| J05 | GET `/api/doctor/appointments` | Doctor 1 | 200, statistics and the complete ordered list equal the fixtures, another doctor's appointment absent. **Replacement** for "doctor dashboard data": no doctor dashboard endpoint exists |
| J06 | GET staff payments dashboard | none | 401 and an empty body, no payment or appointment data (one request, one endpoint: the more sensitive one) |
| J07 | GET staff payments dashboard | Patient | 403, empty body |
| J08 | GET patient dashboard | PharmacyStaff | 403, empty body |
| J09 | **one sampler looped 30 times**: GET staff payments dashboard (the aggregation-heavy endpoint) | PharmacyStaff | every response 200 with values equal to the independent oracle (stable), each within 1500 ms; mean <= 400 ms and p95 <= 750 ms over the 30 samples (checked by the summary) |

**Thresholds** are documented sanity limits for a local development machine, not service levels: 3000 ms per request for J01-J08, 1500 ms per request, 400 ms mean and 750 ms 95th percentile for J09.

## Safety controls
- Isolated database `carenova_appointment_gcn51_qa`, limited user `gcn51_qa`, backend port **5251**, JMeter stop port **4551**. Guards refuse GCN-45/46/47/48 and shared names; ports 3000, 5133-5137, 5199, 5235-5237, 5246-5248 are protected.
- Target host and port are JMeter properties (`gcn51.host`, `gcn51.port`) but **guarded**: anything other than localhost/127.0.0.1 and 5251 makes the sampler target an unreachable `.invalid` address and fails the scenario.
- Secrets (JWT secret, DB password) only in a mode-600 file in a mode-700 folder outside every git work tree; never printed. The MySQL root password is typed by the user and never stored. No credentials in the plan; tokens are minted locally from the environment secret.
- **Read-only**: GET requests only. Read-only SQL proves that every table is identical before and after the run. The backend's own log must show exactly the 38 expected requests, in order, with the expected statuses. Retries 0, redirects off.
- Fixtures are synthetic; every appointment starts at least 9 days away, so nothing depends on the time of day; fixtures are valid 72 hours.
- No production code is modified; nothing is committed or pushed.

## Coverage limitations (not claimed as covered)
- One thread, sequential: no concurrency, load or capacity claim.
- **With one sampler per scenario**: J06 covers the unauthenticated request on the staff dashboard only (the patient dashboard's 401 is covered by the backend xUnit tests), and J09 repeats only the staff dashboard (the patient dashboard is read once, in J01/J02). All nine objectives remain meaningful; nothing was weakened.
- One patient's and one staff view. Admin, the `User` role alias, expired or invalid tokens, the reconciliation exclusion of income and the empty-state dashboards are covered by the backend xUnit tests, not here.
- The medicine-order and medicine-payment dashboards and the real user-auth patient contacts are not part of this backend / environment (J05 asserts contacts are reported unavailable).

## Order of use (every step needs your explicit approval)
1. `gcn51-make-test-secrets.sh`
2. `gcn51-create-database.sh --yes` (you type the MySQL root password)
3. `gcn51-preview-migrations.sh` (offline), then `gcn51-apply-migrations.sh --yes` (8 migrations, 11 tables including the history table)
4. `gcn51-seed-fixtures.sh --yes`
5. `start-gcn51-env.sh --yes`, then `gcn51-preflight.sh`
6. `run-gcn51-jmeter.sh` (plan only), then `run-gcn51-jmeter.sh --yes`
7. `stop-gcn51-env.sh`

Offline checks (no services, no secrets): `validate-gcn51-helpers.sh`, `gcn51-check-assertions.sh`, `gcn51_verifier_selftest.py`.
Regenerate the plan with `gen_gcn51_jmx.py`; never save it from the JMeter GUI and never run it from the GUI against a live backend.
