# GCN-46 Patient Appointments: JMeter performance and security suite

Seven read-only scenarios (JM-01 to JM-07) for the GCN-46 endpoints `GET /api/appointments` and `GET /api/appointments/{id}`. The suite runs against an **isolated local backend** (port 5246) and an **isolated MySQL database** filled with **synthetic patients only**. Every request is a GET; the only writes are the one-off seed INSERTs into the isolated database.

> The response-time numbers are **provisional QA targets, not official product requirements**. They were fixed before the first run (`scenarios.json`) and were never tuned after results.

Results and observations of the QA run are in **[GCN-46-QA-Findings.md](GCN-46-QA-Findings.md)**.

## Scenarios
| ID | Scenario | Load | What is asserted | QA target |
|---|---|---|---|---|
| JM-01 | Patient appointment list under normal load | 10 users x 30 (300), think time ~300 ms | 200, JSON, exactly the patient's 12 seeded appointments with every field equal to the oracle | avg <= 150 ms, p95 <= 400 ms |
| JM-02 | Patient appointment details under normal load | 10 users x 30 (300) over the own 12 ids | 200 and the record equals the seeded one | avg <= 100 ms, p95 <= 300 ms |
| JM-03 | Concurrent list requests | 25 users released together x 4 rounds (100) | 200, each response is exactly its own patient's data (no cross-contamination) | avg <= 400 ms, p95 <= 800 ms |
| JM-04 | Data integrity and categorization under load | edge-case patient: 5 users x 10 x (1 list + 14 details) = 750 | only behaviour the **backend** guarantees: section rule, status and payment labels ("Unavailable" for unknown stored values), `canPay` rule, UTC times, unique ids, exact set. **Order is not asserted** (no ORDER BY; frontend grouping/sorting is not a backend contract) | avg <= 200 ms, p95 <= 500 ms |
| JM-05 | Missing, invalid or expired token handling | 1 user x 5 x 32 (160) | no/empty/garbage/Basic/expired/wrong-secret/wrong-issuer/wrong-audience/`alg none` -> 401 + `WWW-Authenticate: Bearer`; non-GUID or empty subject -> 401 with message; Doctor/Admin/PharmacyStaff -> 403; valid Patient and legacy User -> 200; no data or stack trace in any error body | avg <= 100 ms, p95 <= 300 ms |
| JM-06 | Cross-patient data isolation | patients A and B, 4 users x 5 (320) | each requests the other's 12 ids -> 404 with a body **identical** to a never-existing id (no existence leak); no reference of the other patient anywhere; lists contain only own data; other roles refused. Zero leaks tolerated | avg <= 150 ms, p95 <= 400 ms |
| JM-07 | Increased load, then recovery | baseline 5 users/45 s, increased 10/60 s, peak **20**/60 s, recovery 5/45 s (~8,000 requests) | every response 200 with correct content (10% large-history list of 200 appointments). baseline avg <= 150, p95 <= 400; increased error <= 1%, p95 <= 1500; peak error <= 1%, p95 <= 3000; recovery error 0% and p95 <= max(500 ms, 1.5 x baseline p95). Content failures are always FAIL | per step |

Hard cap per request: 1.5 s (5 s in JM-07). A scenario is **PASS** only if all assertions pass, the sample count equals the expected count, and the targets are met. The summarizer also reports **FAIL**, **BLOCKED** (the SETUP step failed, environment unusable), **STOPPED** (the safety monitor stopped JM-07) and **NOT RUN**.

## Files
| File | Purpose |
|---|---|
| `GCN46PatientAppointmentsTest.jmx`, `gen_gcn46_jmx.py`, `scenarios.json` | the plan, its generator (the single source of the plan) and the targets/expected counts |
| `gen_gcn46_fixtures.py` | synthetic fixtures: `fixtures/fixtures.json` (expected values from an independent oracle of the documented backend rules) and `fixtures/seed-gcn46.sql` (INSERT-only) |
| `gcn46-common.sh` | fixed targets (database, user, port) and guards |
| `gcn46-make-test-secrets.sh`, `gcn46-create-database.sh`, `gcn46-preview-migrations.sh`, `gcn46-apply-migrations.sh`, `gcn46-seed-fixtures.sh` | environment setup (each prints a plan and exits unless `--yes`) |
| `start-gcn46-env.sh`, `stop-gcn46-env.sh` | the backend on port 5246 only |
| `gcn46-validate-env.sh` | read-only validation gate (database, data, authentication, connectivity, plan) |
| `run-gcn46-jmeter.sh`, `gcn46_monitor.py`, `summarize.py`, `gcn46-db-evidence.sh`, `gcn46_token.py` | execution, load-safety monitor, results table, read-only database evidence, token helper for the gate |
| `validate-gcn46-helpers.sh` | static validation: syntax, destructive commands, isolation, secrets, portability, dependencies, shipped content |
| `config/gcn46.properties.example`, `.gitignore` | documented non-secret configuration, git hygiene |

## Prerequisites
`bash`, `python3` (3.8+), `git`, Apache JMeter 5.6.x (`jmeter` on the PATH), a Java runtime for JMeter, a MySQL server and client (tested with MySQL 9.6), the .NET 8 SDK with `dotnet-ef` 8.x (`dotnet tool install --global dotnet-ef --version 8.0.11`), `openssl`, `curl`, `lsof`. For the Groovy compile in the static validator a Java 11-21 runtime is needed (`JAVA_HOME` or `GCN46_JAVA`; Groovy 3 does not run on newer Java) and JMeter's libraries (`JMETER_HOME` or `jmeter` on the PATH).

## Order of use
Run from this folder. Each step that changes something prints a plan first and needs `--yes`.
```bash
cd tests/Performance/GCN-46
bash validate-gcn46-helpers.sh                      # static checks (read-only)
bash gcn46-make-test-secrets.sh                     # 1. random local secrets, outside every git work tree
read -rsp "MySQL admin password: " MYSQL_PWD; echo; export MYSQL_PWD    # bash. zsh: read -rs "?MySQL admin password: " MYSQL_PWD; echo; export MYSQL_PWD
bash gcn46-create-database.sh --yes                 # 2. isolated database + limited user (stops if either exists)
bash gcn46-preview-migrations.sh                    # 3. review gcn46-migrations-preview.sql, then:
bash gcn46-apply-migrations.sh --yes                #    apply to the new database only
bash gcn46-seed-fixtures.sh --yes                   # 4. synthetic data (INSERT only, empty database required)
bash start-gcn46-env.sh --yes                       # 5. publish and start the backend on port 5246
bash gcn46-validate-env.sh                          # 6. validation gate (read-only)
bash run-gcn46-jmeter.sh --phase functional --yes   # 7. JM-01..JM-06
bash run-gcn46-jmeter.sh --phase load --yes         # 8. JM-07 (monitored; close other heavy apps first)
python3 summarize.py --all                          # per-scenario PASS / FAIL / BLOCKED / STOPPED table
bash stop-gcn46-env.sh                              # stop the backend this suite started
```
Results, logs, evidence and generated fixtures are written under this folder and are git-ignored.

## Configuration (environment variables; none are required)
| Variable | Meaning |
|---|---|
| `GCN46_REPO_ROOT` | repository root (default: found with `git rev-parse --show-toplevel`) |
| `GCN46_SECRETS_DIR`, `GCN46_RUN_DIR` | private folders for the secrets file and the published backend (defaults: per-user temp folder; must be outside any git work tree; created with mode 700) |
| `GCN46_EXPECTED_BRANCH` | if set, the scripts refuse to run on another branch |
| `GCN46_MAX_LOAD1` | 1-minute load-average limit of the JM-07 safety monitor (default 9.0, i.e. 90% of a 10-core machine) |
| `GCN46_JAVA`, `JMETER_HOME` | only for the static validator's Groovy compile |
| `MYSQL_USER` | MySQL admin account for database creation (default `root`); its password is read from `MYSQL_PWD` in your own terminal and never stored |

## Isolation and secrets
* Own database `carenova_appointment_gcn46_qa`, limited user `gcn46_qa`, port 5246. The scripts refuse GCN-45/GCN-49 names and ports, shared databases and any `MYSQL_HOST`/`MYSQL_DATABASE` override.
* Secrets (JWT signing secret, database password) are random, written to a mode-600 file in a mode-700 folder **outside every git work tree**, never printed, and reach processes through their environment only. The plan mints synthetic HS256 tokens at run time (same claims, issuer and audience as the real authentication service) from `GCN46_JWT_SECRET`; it contains no secret and no token.
* The plan and scripts contain no machine-specific path. `gcn46-validate-env.sh` and the plan's SETUP step refuse stale fixtures (36-hour validity: upcoming/previous expectations are relative to the seeding time).

## Safe-load rules for JM-07
The run refuses to start when the machine is busy (load >= 6 or free memory < 30% where the OS reports it). While it runs, `gcn46_monitor.py` polls every 5 s and asks JMeter to stop (through its own control port, never by killing a process) when, on two consecutive polls, the 1-minute load exceeds the limit, free memory drops below 10%, the error rate over 10 s exceeds 10%, the 10 s p95 exceeds 5 s, or the backend uses more than 1.5 GB. A stopped run is reported **STOPPED**, not passed. The first run is capped at 20 concurrent users.

## Notes
* Never save the plan from the JMeter GUI: it rewrites the file (and embeds listener file names). Edit `gen_gcn46_jmx.py` and regenerate (`python3 gen_gcn46_jmx.py`). Starting the plan from the GUI without the runner is harmless: the SETUP step stops it before any request is sent.
* Do not point a GUI listener at a file you want to keep: a GUI run writes into it.
* The suite proves nothing about other services or the frontend; payments are out of scope (GCN-45).
