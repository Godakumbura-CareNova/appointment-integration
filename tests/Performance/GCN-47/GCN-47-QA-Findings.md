# GCN-47 Doctor Appointments: JMeter QA findings

## Scope
Five scenarios, five HTTP requests in total (one per scenario, one iteration, no retries, no redirects, no setup/auth/health/teardown requests), run once against an isolated local backend (port 5247) and an isolated MySQL database with synthetic doctors, patients and appointments. Tokens were minted locally. **This is a functional, security and audit check. It is not a load, performance or concurrency test.**

## Recorded run (one formal execution)
| ID | Request | Expected | Actual | Result |
|----|---------|----------|--------|--------|
| JM-01 | GET /api/doctor/appointments (Doctor 1) | 200, strict contract, ordered list, statistics, contactsUnavailable | 200 | PASS |
| JM-02 | GET /api/doctor/appointments/47001 (Doctor 1) | 200, exact 17-field DTO | 200 | PASS |
| JM-03 | GET /api/doctor/appointments/47101 (owned by Doctor 2, Doctor 1 token) | 404, no foreign data | 404 | PASS |
| JM-04 | GET /api/doctor/appointments (Patient role) | 403, empty body | 403 | PASS |
| JM-05 | PATCH /api/doctor/appointments/47002/status (Booked to Confirmed) | 200 `{id,status,updatedAtUtc}` | 200 | PASS |

Independent checks of the same run:
- The backend's own request log showed exactly 5 requests, in the expected order, answered 200, 200, 404, 403, 200.
- Read-only SQL after the run (10 of 10 checks): exactly one audit row (appointment 47002, Doctor 1, Booked to Confirmed); the audit time, the appointment's `UpdatedAtUtc` and the response `updatedAtUtc` are equal to the microsecond; the other 10 appointments and all payments are identical to the seed; no other audit row exists.

## Caveats about the evidence
- After the formal run, a JMeter GUI window ran the saved plan again. The backend log then contained 9 requests instead of 5. The four extra requests were GETs answered 401 (the GUI had no signing secret, so no token was minted); the other three scenarios failed in the GUI on an unresolved variable before reaching the server. The GUI also overwrote the summary CSV and re-saved the plan file. The formal run's own integrity checks (5 samples, 5 server requests, database checks) were completed before this and passed. The plan in this repository was regenerated from the generator, not taken from the GUI.
- The raw results, logs and screenshots are local and are not committed.

## Coverage limitations (not claimed as covered)
- No concurrency or load coverage: five sequential requests prove nothing about throughput, contention or races. The 3000 ms assertion is a sanity cap only.
- JM-03 is a single cross-doctor read: no repeats, no concurrent access, no cross-doctor PATCH, no comparison with a non-existent id (enumeration resistance).
- JM-04 covers only the Patient role (403). Missing token (401), invalid or expired tokens, Admin and PharmacyStaff are not covered.
- No "today" appointments are seeded, so same-day flags are only partly exercised.
- Patient contact enrichment is not covered (user-auth service absent; `contactsUnavailable: true` is asserted).
- PATCH stale-update (409), invalid-transition (400) and unknown-id (404) paths are left to the backend integration tests.
- Each run changes one row, so every run needs a new empty database; fixtures are valid for 36 hours.
