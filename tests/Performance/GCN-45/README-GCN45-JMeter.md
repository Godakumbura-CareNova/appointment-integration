# GCN-45 JMeter environment: helper scripts (PREPARED, NOT EXECUTED)

Order of use (each step needs its own approval; nothing here has been run):
1. `gcn45-make-test-secrets.sh`        random local test secrets (outside every repo)
2. `gcn45-create-database.sh [--yes]`  database `carenova_appointment_gcn45_qa` + limited user `gcn45_qa` (root password typed by you)
3. `gcn45-preview-migrations.sh`       SQL of all 4 migrations for review (offline)
4. `gcn45-apply-migrations.sh [--yes]` apply to the new database only, as `gcn45_qa`
5. `start-gcn45-jmeter-env.sh [--yes]` doctor stub :5235, backend A :5236, backend B :5237 (stop with `stop-gcn45-jmeter-env.sh`)
6. `run-gcn45-jmeter.sh --phase seed|readonly|state|concurrent [--yes]`  one phase per approval
7. `gcn45-db-evidence.sh <label>`       read-only counts and duplicate checks (also run automatically after each phase)
Support: `gcn45-common.sh` (fixed targets and guards), `gcn45-doctor-stub.py`, `gen_gcn45_jmx.py` -> `GCN45AppointmentPaymentTest.jmx` + `scenarios.json`, `summarize.py`, `validate-gcn45-helpers.sh` (static checks, already run: `logs/validate-gcn45-helpers.txt`), `known-defects/GCN-45-known-defects.md`.

Every script that changes something prints a plan and exits unless `--yes` is given.

## Changes from the approved plan (all deliberate, none weaken an assertion)
- The migration file is the plain full script (empty database to latest), not `--idempotent`: Pomelo's idempotent script uses a stored procedure (CREATE/DROP PROCEDURE), which the static safety scan forbids; the database is new and empty so idempotency is not needed.
- JM-08 outage step asserts "5xx class, within 5 s, a message, no internal detail, nothing saved" and does not pin the exact generic message, so a correct fix of GCN45-D1 (503) does not make the scenario fail. The strict 503 expectation stays in the known-defect repro.
- Per-sample hard cap: every product request also carries a 3 s (5 s for concurrent/outage steps) duration assertion in addition to the avg/p95 thresholds.
- The JMeter plan contains fixture seeding (`FX`), an environment check (`SETUP`) and a stub reset (`ENV`) as support steps; they are reported but are not among the eight scored scenarios.
