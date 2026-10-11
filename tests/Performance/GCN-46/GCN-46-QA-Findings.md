# GCN-46 Patient Appointments: QA performance and security findings

Suite: `tests/Performance/GCN-46/` (Apache JMeter 5.6.3, see README). Branch `feature/GCN-46-patient-appointments`, backend commit `1ad3d54`.
Environment of the QA run: local isolated backend (Release build, Staging configuration), isolated MySQL 9.6.0 database with 24 synthetic patients, 478 appointments and 434 payments, Apple Silicon laptop (10 cores, 16 GB), JMeter on Java 21. All numbers are single-machine local figures.
The response-time numbers are **provisional QA targets, not official product requirements**; they were fixed before the first run and never tuned.

## 1. Final status

| ID | Scenario | Status | Requests | Passed | Failed | Avg (ms) | p95 (ms) | Max (ms) | Throughput (req/s) | QA target (avg / p95) |
|---|---|---|---|---|---|---|---|---|---|---|
| JM-01 | Patient appointment list under normal load | **PASS** | 300 | 300 | 0 | 13 | 20 | 37 | 22.0 | 150 / 400 |
| JM-02 | Patient appointment details under normal load | **PASS** | 300 | 300 | 0 | 13 | 20 | 25 | 22.1 | 100 / 300 |
| JM-03 | Concurrent patient appointment list requests (25 users) | **PASS** | 100 | 100 | 0 | 58 | 82 | 88 | 335.6 | 400 / 800 |
| JM-04 | Data integrity and categorization under load | **PASS** | 750 | 750 | 0 | 8 | 13 | 29 | 264.0 | 200 / 500 |
| JM-05 | Missing, invalid or expired token handling | **PASS** | 160 | 160 | 0 | 2 | 10 | 12 | 382.8 | 100 / 300 |
| JM-06 | Cross-patient data isolation | **PASS** | 320 | 320 | 0 | 8 | 13 | 15 | 415.0 | 150 / 400 |
| JM-07 | Increased load, then recovery | **NOT RUN** | 0 | 0 | 0 | n/a | n/a | n/a | n/a | per step, see README |

**Six of seven scenarios were executed and passed (1,930 requests, 0 failures, 0% errors). JM-07 has not been executed**, so no result and no pass is claimed for it. It needs a separate decision: it is the only load scenario, capped at 20 concurrent users for its first run, and it is run through the safety-monitored runner (`run-gcn46-jmeter.sh --phase load`).

Final functional run: 1,930 HTTP requests plus the SETUP check in 46 seconds. Overall average 12 ms, p95 45 ms, maximum 88 ms. Response codes: JM-05 401 x110, 403 x30, 200 x20; JM-06 404 x280, 200 x20, 403 x20; all other requests 200.

## 2. What was verified

* **JM-01 / JM-02 / JM-03:** every response is exactly the calling patient's 12 seeded appointments (list) or the requested one (details), every field equal to an independent oracle of the documented backend rules (reference, doctor, UTC times with a `Z` suffix, status, section, payment method and status, `canPay`). 25 simultaneous users each received only their own data.
* **JM-04:** the backend rules held on all 750 requests for a patient with 14 edge-case appointments: Completed and Cancelled are Previous even in the future; an ended Booked appointment is Previous; an unknown stored status or an end time before the start time is Unavailable; unknown stored payment method or status values are reported as "Unavailable"; `canPay` is false for Successful, ReceiptUnderVerification and unknown payment states and true for upcoming appointments otherwise. List and details agree. Order is deliberately not asserted.
* **JM-05:** the 14 invalid-credential and wrong-role cases, on both endpoints, are all refused with the right status (401 with `WWW-Authenticate: Bearer`, 401 with the identity message, 403) and no response contains appointment data or stack-trace text. Valid `Patient` and legacy `User` tokens are accepted. The unsigned `alg: none` token, wrong signing secret, wrong issuer, wrong audience and expired token are all rejected.
* **JM-06:** 240 cross-patient requests (each of the other patient's 12 appointment ids, ten times) all returned 404 with a body identical to the body for a never-existing id, so the API does not reveal whether another patient's appointment exists. No reference of the other patient appeared in any response; each patient's list contained only that patient's data; a Doctor token was refused with 403.
* **Database:** row counts and contents were identical before and after every run (478 appointments, 434 payments, 0 receipts, 0 attempts, no updated rows, no duplicates), confirming the suite is read-only.

## 3. Run history (one test-script defect found and fixed)

* **Run 1 (functional): JM-01 to JM-05 PASS, JM-06 FAIL (170 of 320 requests passed).** All 150 failures involved one synthetic patient's first appointment, which the plan used as `null` (requests to `/api/appointments/null`). The backend answered correctly every time. Root cause: a **defect in the test script, not in the application**: fixtures were parsed with Groovy's `JsonSlurper`, which returns lazily built maps that are not thread-safe; four threads reading them for the first time at the same moment got a null. Offline reproduction: a corrupted read in 220 of 300 concurrent first-read trials with the lazy structure, and in 0 of 300 after materializing it once.
* **Fix:** the SETUP script converts the fixtures to plain maps and lists once, in a single thread. Nothing else changed: the program compared every sampler, assertion, duration cap, timer, thread group, path and header of both plan versions, and only that one script differs. Thresholds and expected counts are unchanged.
* **Run 2 (functional, final): JM-01 to JM-06 all PASS** (table above). The JM-06 isolation assertions were additionally shown to detect leaks by running the plan's own assertion scripts offline against deliberately leaking responses (the other patient's appointment in a 404 or in a list, a different 404 message, a missing appointment): every leak was detected and every correct response was accepted.
* **Safety check of the plan's design:** starting the plan from the JMeter GUI without the runner (no phase property) stopped at the SETUP step with "property phase must be functional or load" before any request was sent; the database was unchanged.

## 4. Observations and unresolved items

| ID | Type | Observation | Status |
|---|---|---|---|
| GCN46-NR | Not run | **JM-07 (increased load and recovery) was not executed.** | Open: needs a decision to run it with the safety monitor. |
| GCN46-O1 | Design observation | `PatientAppointmentService` has no `ORDER BY`; grouping and sorting are done by the frontend. The API returned ascending id order in every observed response (1 distinct order across the 50 list responses of the edge-case patient), but order is not a contract. | Observation only. The suite asserts the list as a set. Developers may add an explicit order if ordering is intended to be guaranteed. |
| GCN46-O2 | Performance risk | `GET /api/appointments` is not paginated, so the response grows with a patient's history. A patient with 200 appointments gets about 58 KB per list (about 20 ms in a single local request). | Observation. Only JM-07 would measure this under load. |
| GCN46-O4 | Scalability observation | The generated schema has no index on `Appointments.PatientId`, although both endpoints filter by it (only `AppointmentReference` and `DoctorAvailabilitySlotId` are indexed). With about 480 rows this cannot show in timings; at larger volumes both endpoints would scan the table. | Observation for the developers; not measurable with this data size, so the suite makes no scalability claim. |
| GCN46-O3 | Out of scope | Findings of GCN-45 (payments) are not part of this suite. | Not tested here. |

No application defect was found by JM-01 to JM-06.

## 5. Limits of this QA run

* Only the read endpoints of GCN-46 were tested; the frontend and other services were not.
* About 480 synthetic rows and one local machine: the numbers say nothing about production volumes or hardware.
* Expected values come from an oracle written from the documented backend rules and checked against the developers' xUnit rule table; if the intended rules differ from the implementation, the oracle would need to change, not the thresholds.
* JM-07 is unexecuted (see section 1).

## 6. Reproducing

See the README. In short: `cd tests/Performance/GCN-46`, run the setup scripts in order, then `bash run-gcn46-jmeter.sh --phase functional --yes` and `python3 summarize.py --all`.
