# GCN-45 JMeter: environment plan and 8 scenarios (PLAN ONLY, nothing executed or changed)

## 1. Findings (read-only inspection)
- Backend config comes only from environment/appsettings: `ConnectionStrings:DefaultConnection`, `JwtSettings:Secret/Issuer/Audience` (Issuer `CareNova.UserAuth`, Audience `CareNova.Client` default), `DoctorPaymentService:BaseUrl`, `PayHere:*`. With an empty JWT secret no authentication is registered, so a test secret is mandatory.
- JWT: HS256, validated issuer/audience/lifetime. user-auth emits `sub` + `NameIdentifier` (patient id), `ClaimTypes.Role`. The test tokens will be minted the same way with a throw-away secret.
- Appointments are created by the real `POST /api/appointments {doctorId, slotId}`: the backend calls the doctor service `GET api/doctors/{id}` (forwarding the bearer token), takes the slot from `upcomingSlots` (must start in the future) and the fee from `consultationFee`. A slot can be booked once (unique slot index). So a local doctor stub with many future slots makes safe, repeatable data. No auth service, no pharmacy service, no Kafka registration in Program.cs is needed.
- Payment is PayHere sandbox with LOCAL signing: no outbound call; the notification is a form POST verified by MD5 (`md5sig`), so JMeter can sign test notifications itself with a test secret.
- Azure Blob is not configured: receipt upload and the staff file download cannot work, so they are excluded (covered by xUnit with in-memory storage).
- Migrations (the new database is empty, so all four are needed, all additive; `DropTable` only in `Down()`):
  1. `20261006174540_InitialAppointmentBooking`: table `Appointments`, indexes on AppointmentReference and DoctorAvailabilitySlotId
  2. `20261007031240_GCN45AppointmentPayments`: `AppointmentPayments`, FK to Appointments (cascade), unique index AppointmentId
  3. `20261007041047_GCN45AppointmentReceipts`: `AppointmentReceipts`, FK to AppointmentPayments (cascade)
  4. `20261007054830_GCN45OnlinePaymentAttempts`: `AppointmentOnlinePaymentAttempts`, FK to AppointmentPayments (cascade), unique GatewayReference
  `dotnet-ef 8.0.11` is installed. MySQL listens on 127.0.0.1:3306 (the shared server; the new database is separate).

## 2. Processes
| Process | Now | Plan |
|---|---|---|
| GCN-49 backend :5136 (pid 56708, stale build, shared QA DB) | running | **keep running, untouched**; GCN-45 uses other ports |
| GCN-49 stub :5199 (pid 56676) | running | **keep running**, unused |
| Vite :3000 (pid 50545) | running | keep running, not used by JMeter |
| MySQL :3306 | running | keep; only the new database and a limited user are added |
| GCN-45 backend A :5236 (PayHere test config) | new | start from a `dotnet publish` copy (leaves `bin/Debug` of the running build untouched) |
| GCN-45 backend B :5237 (PayHere NOT configured) | new | only for the gateway-unavailable check in JM-08 |
| Doctor stub :5235 (new `gcn45-doctor-stub.py`) | new | modes ok / nofee / down / slow, many future slots, records whether a bearer token was forwarded |
Nothing needs to be stopped.

## 3. Setup commands (NOT executed; each needs approval)
```bash
# A. test secrets (random, local only, mode 600, outside any repository)
bash ~/carenova/qa-reports/GCN-45/jmeter/gcn45-make-test-secrets.sh        # writes ~/.gcn45-jmeter.env
# B. create the isolated database and a limited user (you type the root password silently; it is never saved)
read -rs "?MySQL root password: " MYSQL_PWD; echo; export MYSQL_PWD
bash ~/carenova/qa-reports/GCN-45/jmeter/gcn45-create-database.sh          # refuses if the database already exists
# C. migrations: preview first, then apply to the NEW database only
cd ~/carenova/appointment-integration && dotnet ef migrations script --idempotent --project src/AppointmentIntegration.Api -o ~/carenova/qa-reports/GCN-45/jmeter/gcn45-migrations-preview.sql
bash ~/carenova/qa-reports/GCN-45/jmeter/gcn45-apply-migrations.sh         # dotnet ef database update --connection <new DB, limited user>
# D. start the local services (stub, backend A, backend B)
bash ~/carenova/qa-reports/GCN-45/jmeter/start-gcn45-jmeter-env.sh
# E. run (after the approvals in section 6)
bash ~/carenova/qa-reports/GCN-45/jmeter/run-gcn45-jmeter.sh --phase seed|readonly|state|concurrent
```
SQL run in B (no existing object is touched): `CREATE DATABASE carenova_appointment_gcn45_qa CHARACTER SET utf8mb4; CREATE USER 'gcn45_qa'@'localhost' IDENTIFIED BY '<random>'; GRANT ALL ON carenova_appointment_gcn45_qa.* TO 'gcn45_qa'@'localhost';`
Backend environment: `ConnectionStrings__DefaultConnection` (new DB, limited user), `JwtSettings__Secret` (throw-away), `DoctorPaymentService__BaseUrl=http://localhost:5235`, `PayHere__MerchantId=TEST123`, `PayHere__MerchantSecret=<throw-away>`, `PayHere__Sandbox=true`, `PayHere__AllowLivePayments=false`, `PayHere__NotifyUrl=http://localhost:5236/api/appointment-payments/payhere/notify`, `PayHere__FrontendBaseUrl=http://localhost:3000`. Backend B: same but `PayHere__MerchantSecret` empty.
Rollback: stop the three new processes; `DROP DATABASE carenova_appointment_gcn45_qa; DROP USER 'gcn45_qa'@'localhost'` (only on your request; it contains test data only).

## 4. Data safety
Appointments are created through the real API against the stub doctor, only in the new database, with GUID patients that exist nowhere else. Estimated volume: about 30 appointments, 25 payments, 6 attempts; no real money, no real PayHere, no receipts. Fixture phase (outside the 8 scenarios, with its own assertions, aborts the run if it fails): F1 patient P1, Cash selected; F2 patient P1, gateway selected with attempt 1 started; F3 patient P2, appointment without payment.

## 5. Scenarios
Each scenario is its own thread group with labels `JM-0N-...`. Every sample asserts the exact expected status code; response-body assertions check fields and exact messages; no sample is "allowed" to be an error. Performance thresholds are fixed before the run (local machine): reads avg <= 300 ms and p95 <= 800 ms; writes avg <= 600 ms and p95 <= 1500 ms; any 5xx where not expected = FAIL. A scenario is PASS only if all its samples pass, the sample count equals the expected count (a skipped sample is a FAIL), and the aggregate thresholds hold. `summarize.py` prints one PASS/FAIL/BLOCKED row per scenario from the JTL.

### Read-only group (GET, or POSTs that are rejected without changing state; run on the seeded fixtures)
| ID | Scenario | Key assertions |
|---|---|---|
| JM-01 | Payment status read under load: 5 users x 20 `GET /api/appointments/{F1}/payment` | 200 x100; JSON: appointmentId, appointmentReference, amount 2700, method Cash, status Pending; read thresholds; 0% error |
| JM-02 | Authorization and ownership matrix on the same GET | no token 401; garbage token 401; expired token 401; token signed with another secret 401; subject not a GUID 401 "A valid patient identity is required."; other patient 404 and the body IDENTICAL to an unknown appointment (id 999999) (no existence leak); id 0 and `abc` 404; owner without payment (F3) 404; no body contains a stack trace or exception text |
| JM-03 | Staff authorization and read performance: `GET /api/staff/appointment-payments/receipts` | PharmacyStaff 200 + JSON array; Patient, Doctor, Admin 403; anonymous 401; `POST .../appointments/999999/receipt/verify` staff 404, patient 403; 5 users x 20 list reads meet read thresholds. (The spaced "Pharmacy Staff" role is GCN45-D2, kept out of the scored run.) |
| JM-04 | Online attempt read and webhook rejection (no state change) | `GET .../online/{F2 attempt}` owner 200 `outcome` Processing; other patient 404; unknown attempt 404; `POST /api/appointment-payments/payhere/notify`: bad md5sig 400; missing md5sig 400; body over 64 KB rejected (413); correctly signed notification for an unknown order 200 and ignored; afterwards `GET` of F2 still `AwaitingGatewayPayment` and the attempt still Processing. Expected values for the missing-signature and oversize cases come from the controller/gateway code; a mismatch is reported as a finding, not adjusted. |

### State-changing group (creates appointments and payment rows; needs approval)
| ID | Scenario | Key assertions |
|---|---|---|
| JM-05 | Booking, method selection and business rules | `POST /api/appointments` 201 with a stub slot; select Cash 200 Pending 2700; switch to BankTransfer 200 AwaitingBankTransferReceipt; `GET` shows BankTransfer; invalid/blank/"Crypto"/"99" method 400 "Select a valid payment method"; same slot booked twice 409; stub in `nofee` mode: 409 "consultation fee has not been configured" and no payment row; every write meets write thresholds |
| JM-06 | Online payment lifecycle and duplicate handling | select PaymentGateway; start attempt 1 200: sandbox true, merchantId TEST123, amount "2700.00", currency LKR, `hash` equals MD5(merchant+order+amount+currency+MD5(secret)) computed independently in Groovy; signed failed notification (-2) then result Failed canRetry; attempt 2 has a new order id; signed success (2) then result Succeeded and payment Successful; the same success notification replayed: 200, state unchanged, still ONE Successful payment; a late failure for attempt 1 cannot undo it; start again after paid 409 "already been paid"; select a method after paid 409; tampered amount on a fresh attempt is Failed (not Successful) |

### Concurrent (needs separate approval)
| ID | Scenario | Key assertions |
|---|---|---|
| JM-07 | Concurrency (5 threads released together by a synchronizing timer) | A: 5 first-time method selections on the SAME fresh appointment: only 200 or 409 (never 500), at least one 200, final `GET` shows one consistent payment (single method); B: 5 identical signed success notifications for one attempt: all 200, one Successful payment; C: 5 different patients/appointments selecting methods in parallel: all 200 within write thresholds. After the run a read-only SQL count (appointments, payments, attempts) is saved as evidence. |

### Service failure and recovery (state-changing, needs approval)
| ID | Scenario | Key assertions |
|---|---|---|
| JM-08 | Dependency failure, graceful behaviour and recovery | doctor stub `down`: method selection returns a server error (5xx), within 5 s, with the generic message "Payment could not be processed. Please try again." and no stack trace; no payment row is created or changed; `GET` payment (does not use the doctor service) still 200; stub back `ok`: the same request 200 (recovery). Backend B (PayHere not configured): `POST .../online/start` 503 with `retryable: true`; backend A, same request: 200. The strict "outage must be 503" expectation is GCN45-D1 (OPEN) and is NOT scored here; it stays in the known-defect repro (optional extra sample `KD-D1`, excluded from the 8, which would FAIL today). |

## 6. Approvals needed (each separate)
1. Create `carenova_appointment_gcn45_qa` and the limited user `gcn45_qa` (needs your root password typed by you).
2. Apply the four migrations to that database only (after you review the preview script).
3. Start the doctor stub (5235) and backends A (5236) and B (5237); nothing existing is stopped.
4. Seed the fixtures (about 3 appointments, 2 payments, 1 attempt).
5. Run the read-only group (JM-01..04).
6. Run the state-changing group (JM-05, JM-06, JM-08).
7. Run the concurrent group (JM-07).

## 7. Risks
- The MySQL server is shared; isolation is by database and user, and the limited user cannot touch other databases.
- Rows cannot be deleted by the tests; the database is disposable (drop on request).
- JM-07A depends on the unique index (no row version): the expected 409 mapping could show a real 500 (would be a genuine defect, reported, not hidden).
- Read-only scenarios still depend on seeded rows, so the "seed" phase is state-changing.
- Webhook signing in JMeter uses the throw-away test secret, never a PayHere credential; the secret file is outside the repositories and reports.
- The stale GCN-49 backend keeps using the shared QA database; it is not touched.
- Performance numbers are local single-machine figures; thresholds are fixed beforehand and not tuned after results.
- Doctor stub and test tokens are QA tooling only; no production code changes.
