#!/usr/bin/env bash
# Generates the synthetic fixtures (gen_gcn48_fixtures.py) and INSERTS them into the isolated database carenova_appointment_gcn48_qa as the limited user.
#   bash gcn48-seed-fixtures.sh          plan only (no database access)       bash gcn48-seed-fixtures.sh --yes    seeds
# Safety: INSERT-only SQL (re-checked by gcn48_seed_is_insert_only and the forbidden-statement scan), applied to ONE database by name; the Appointments table must be
# EMPTY (otherwise it stops: it never adds to or replaces existing data); a previous fixtures.json is moved aside, never overwritten. Synthetic data only.
set -u -o pipefail
. "$(dirname "$0")/gcn48-common.sh"
gcn48_assert_db_target
FX="$GCN48_DIR/fixtures"; TS="$(date +%Y%m%d-%H%M%S)"
if [ "${1:-}" != "--yes" ]; then
  echo "PLAN (nothing executed): generate $FX/fixtures.json and $FX/seed-gcn48.sql (8 synthetic appointments of two patients and 7 payments), then INSERT them into $GCN48_DB_NAME as $GCN48_DB_USER if the Appointments table is empty."
  echo "Fixtures are valid for 36 hours (upcoming/previous expectations drift afterwards); re-seeding needs a new empty database."; exit 0
fi
gcn48_load_secrets
VISIBLE=$(gcn48_mysql_app -N -B -e "SHOW DATABASES;" | tr '\n' ' ') || gcn48_die "cannot connect as $GCN48_DB_USER"
case "$VISIBLE" in *"$GCN48_DB_NAME"*) ;; *) gcn48_die "$GCN48_DB_NAME not visible to $GCN48_DB_USER";; esac
HAS=$(gcn48_mysql_app -N -B "$GCN48_DB_NAME" -e "SELECT (SELECT COUNT(*) FROM Appointments) + (SELECT COUNT(*) FROM AppointmentPayments) + (SELECT COUNT(*) FROM AppointmentStatusChanges) + (SELECT COUNT(*) FROM AppointmentCancellations) + (SELECT COUNT(*) FROM RefundRecords) + (SELECT COUNT(*) FROM AppointmentPaymentReconciliations);") || gcn48_die "tables not found: apply the migrations first (the GCN-48 audit table AppointmentStatusChanges must exist)"
[ "$HAS" = "0" ] || gcn48_die "the database already contains $HAS rows (appointments, payments, audit or cancellation rows); refusing to add to existing data. The scenarios change one row, so every run needs a NEW empty database."
mkdir -p "$FX"; for f in fixtures.json seed-gcn48.sql; do [ -e "$FX/$f" ] && mv "$FX/$f" "$FX/previous-$TS-$f"; done
python3 "$GCN48_DIR/gen_gcn48_fixtures.py" --out-dir "$FX" || gcn48_die "fixture generation failed"
gcn48_seed_is_insert_only "$FX/seed-gcn48.sql" || gcn48_die "seed SQL is not insert-only"
gcn48_sql_is_safe "$FX/seed-gcn48.sql" || gcn48_die "seed SQL contains a forbidden statement"
{
  echo "GCN-48 seed - $(date '+%Y-%m-%d %H:%M:%S')"
  gcn48_mysql_app "$GCN48_DB_NAME" < "$FX/seed-gcn48.sql" || gcn48_die "seeding failed (the file runs in one transaction; check the counts before retrying)"
  EXP_A=$(python3 -c "import json;print(json.load(open('$FX/fixtures.json'))['counts']['appointments'])"); EXP_P=$(python3 -c "import json;print(json.load(open('$FX/fixtures.json'))['counts']['payments'])")
  GOT_A=$(gcn48_mysql_app -N -B "$GCN48_DB_NAME" -e "SELECT COUNT(*) FROM Appointments;"); GOT_P=$(gcn48_mysql_app -N -B "$GCN48_DB_NAME" -e "SELECT COUNT(*) FROM AppointmentPayments;")
  echo "appointments: $GOT_A (expected $EXP_A)   payments: $GOT_P (expected $EXP_P)"
  [ "$GOT_P" = "$EXP_P" ] || gcn48_die "payment count differs from the fixtures"
  [ "$GOT_A" = "$EXP_A" ] || gcn48_die "appointment count differs from the fixtures"
  echo "Seeded. Next: bash $GCN48_DIR/start-gcn48-env.sh --yes   (then gcn48-preflight.sh; no HTTP request is made by any setup script)"
} 2>&1 | tee "$GCN48_DIR/logs/seed-fixtures.log"
