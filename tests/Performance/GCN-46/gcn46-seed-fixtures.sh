#!/usr/bin/env bash
# Generates the synthetic fixtures (gen_gcn46_fixtures.py) and INSERTS them into the isolated database carenova_appointment_gcn46_qa as the limited user.
#   bash gcn46-seed-fixtures.sh          plan only (no database access)       bash gcn46-seed-fixtures.sh --yes    seeds
# Safety: INSERT-only SQL (re-checked by gcn46_seed_is_insert_only and the forbidden-statement scan), applied to ONE database by name; the Appointments table must be
# EMPTY (otherwise it stops: it never adds to or replaces existing data); a previous fixtures.json is moved aside, never overwritten. Synthetic data only.
set -u -o pipefail
. "$(dirname "$0")/gcn46-common.sh"
gcn46_assert_db_target
FX="$GCN46_DIR/fixtures"; TS="$(date +%Y%m%d-%H%M%S)"
if [ "${1:-}" != "--yes" ]; then
  echo "PLAN (nothing executed): generate $FX/fixtures.json and $FX/seed-gcn46.sql (about 478 synthetic appointments, 434 payments), then INSERT them into $GCN46_DB_NAME as $GCN46_DB_USER if the Appointments table is empty."
  echo "Fixtures are valid for 36 hours (upcoming/previous expectations drift afterwards); re-seeding needs a new empty database."; exit 0
fi
gcn46_load_secrets
VISIBLE=$(gcn46_mysql_app -N -B -e "SHOW DATABASES;" | tr '\n' ' ') || gcn46_die "cannot connect as $GCN46_DB_USER"
case "$VISIBLE" in *"$GCN46_DB_NAME"*) ;; *) gcn46_die "$GCN46_DB_NAME not visible to $GCN46_DB_USER";; esac
HAS=$(gcn46_mysql_app -N -B "$GCN46_DB_NAME" -e "SELECT COUNT(*) FROM Appointments;") || gcn46_die "Appointments table not found: apply the migrations first"
[ "$HAS" = "0" ] || gcn46_die "Appointments already contains $HAS rows; refusing to add to existing data."
mkdir -p "$FX"; for f in fixtures.json seed-gcn46.sql; do [ -e "$FX/$f" ] && mv "$FX/$f" "$FX/previous-$TS-$f"; done
python3 "$GCN46_DIR/gen_gcn46_fixtures.py" --out-dir "$FX" || gcn46_die "fixture generation failed"
gcn46_seed_is_insert_only "$FX/seed-gcn46.sql" || gcn46_die "seed SQL is not insert-only"
gcn46_sql_is_safe "$FX/seed-gcn46.sql" || gcn46_die "seed SQL contains a forbidden statement"
{
  echo "GCN-46 seed - $(date '+%Y-%m-%d %H:%M:%S')"
  gcn46_mysql_app "$GCN46_DB_NAME" < "$FX/seed-gcn46.sql" || gcn46_die "seeding failed (the file runs in one transaction; check the counts before retrying)"
  EXP_A=$(python3 -c "import json;print(sum(len(p['appointments']) for p in json.load(open('$FX/fixtures.json'))['patients'].values()))")
  GOT_A=$(gcn46_mysql_app -N -B "$GCN46_DB_NAME" -e "SELECT COUNT(*) FROM Appointments;"); GOT_P=$(gcn46_mysql_app -N -B "$GCN46_DB_NAME" -e "SELECT COUNT(*) FROM AppointmentPayments;")
  echo "appointments: $GOT_A (expected $EXP_A)   payments: $GOT_P"
  [ "$GOT_A" = "$EXP_A" ] || gcn46_die "appointment count differs from the fixtures"
  echo "Seeded. Next: bash $GCN46_DIR/start-gcn46-env.sh --yes   (then gcn46-validate-env.sh)"
} 2>&1 | tee "$GCN46_DIR/logs/seed-fixtures.log"
