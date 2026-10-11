#!/usr/bin/env bash
# Generates the synthetic fixtures (gen_gcn47_fixtures.py) and INSERTS them into the isolated database carenova_appointment_gcn47_qa as the limited user.
#   bash gcn47-seed-fixtures.sh          plan only (no database access)       bash gcn47-seed-fixtures.sh --yes    seeds
# Safety: INSERT-only SQL (re-checked by gcn47_seed_is_insert_only and the forbidden-statement scan), applied to ONE database by name; the Appointments table must be
# EMPTY (otherwise it stops: it never adds to or replaces existing data); a previous fixtures.json is moved aside, never overwritten. Synthetic data only.
set -u -o pipefail
. "$(dirname "$0")/gcn47-common.sh"
gcn47_assert_db_target
FX="$GCN47_DIR/fixtures"; TS="$(date +%Y%m%d-%H%M%S)"
if [ "${1:-}" != "--yes" ]; then
  echo "PLAN (nothing executed): generate $FX/fixtures.json and $FX/seed-gcn47.sql (11 synthetic appointments of two doctors and 7 payments), then INSERT them into $GCN47_DB_NAME as $GCN47_DB_USER if the Appointments table is empty."
  echo "Fixtures are valid for 36 hours (upcoming/previous expectations drift afterwards); re-seeding needs a new empty database."; exit 0
fi
gcn47_load_secrets
VISIBLE=$(gcn47_mysql_app -N -B -e "SHOW DATABASES;" | tr '\n' ' ') || gcn47_die "cannot connect as $GCN47_DB_USER"
case "$VISIBLE" in *"$GCN47_DB_NAME"*) ;; *) gcn47_die "$GCN47_DB_NAME not visible to $GCN47_DB_USER";; esac
HAS=$(gcn47_mysql_app -N -B "$GCN47_DB_NAME" -e "SELECT (SELECT COUNT(*) FROM Appointments) + (SELECT COUNT(*) FROM AppointmentPayments) + (SELECT COUNT(*) FROM AppointmentStatusChanges);") || gcn47_die "tables not found: apply the migrations first (the GCN-47 audit table AppointmentStatusChanges must exist)"
[ "$HAS" = "0" ] || gcn47_die "the database already contains $HAS rows (appointments, payments or audit rows); refusing to add to existing data. The scenarios change one row, so every run needs a NEW empty database."
mkdir -p "$FX"; for f in fixtures.json seed-gcn47.sql; do [ -e "$FX/$f" ] && mv "$FX/$f" "$FX/previous-$TS-$f"; done
python3 "$GCN47_DIR/gen_gcn47_fixtures.py" --out-dir "$FX" || gcn47_die "fixture generation failed"
gcn47_seed_is_insert_only "$FX/seed-gcn47.sql" || gcn47_die "seed SQL is not insert-only"
gcn47_sql_is_safe "$FX/seed-gcn47.sql" || gcn47_die "seed SQL contains a forbidden statement"
{
  echo "GCN-47 seed - $(date '+%Y-%m-%d %H:%M:%S')"
  gcn47_mysql_app "$GCN47_DB_NAME" < "$FX/seed-gcn47.sql" || gcn47_die "seeding failed (the file runs in one transaction; check the counts before retrying)"
  EXP_A=$(python3 -c "import json;d=json.load(open('$FX/fixtures.json'))['doctors'];print(sum(len(v['appointments']) for v in d.values()))")
  GOT_A=$(gcn47_mysql_app -N -B "$GCN47_DB_NAME" -e "SELECT COUNT(*) FROM Appointments;"); GOT_P=$(gcn47_mysql_app -N -B "$GCN47_DB_NAME" -e "SELECT COUNT(*) FROM AppointmentPayments;")
  echo "appointments: $GOT_A (expected $EXP_A)   payments: $GOT_P (expected 7)"
  [ "$GOT_P" = "7" ] || gcn47_die "payment count differs from the fixtures"
  [ "$GOT_A" = "$EXP_A" ] || gcn47_die "appointment count differs from the fixtures"
  echo "Seeded. Next: bash $GCN47_DIR/start-gcn47-env.sh --yes   (then gcn47-preflight.sh; no HTTP request is made by any setup script)"
} 2>&1 | tee "$GCN47_DIR/logs/seed-fixtures.log"
