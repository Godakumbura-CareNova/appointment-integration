#!/usr/bin/env bash
# Generates the synthetic fixtures (gen_gcn51_fixtures.py) and INSERTS them into the isolated database carenova_appointment_gcn51_qa as the limited user.
#   bash gcn51-seed-fixtures.sh          plan only (no database access)       bash gcn51-seed-fixtures.sh --yes    seeds
# Safety: INSERT-only SQL (re-checked by gcn51_seed_is_insert_only and the forbidden-statement scan), applied to ONE database by name; the Appointments table must be
# EMPTY (otherwise it stops: it never adds to or replaces existing data); a previous fixtures.json is moved aside, never overwritten. Synthetic data only.
set -u -o pipefail
. "$(dirname "$0")/gcn51-common.sh"
gcn51_assert_db_target
FX="$GCN51_DIR/fixtures"; TS="$(date +%Y%m%d-%H%M%S)"
if [ "${1:-}" != "--yes" ]; then
  echo "PLAN (nothing executed): generate $FX/fixtures.json and $FX/seed-gcn51.sql (synthetic appointments, payments and receipts of four patients and two doctors), then INSERT them into $GCN51_DB_NAME as $GCN51_DB_USER if the Appointments table is empty."
  echo "Fixtures are valid for 72 hours (every start is at least 9 days away); the suite is read-only, but a fresh empty database is still required for seeding."; exit 0
fi
gcn51_load_secrets
VISIBLE=$(gcn51_mysql_app -N -B -e "SHOW DATABASES;" | tr '\n' ' ') || gcn51_die "cannot connect as $GCN51_DB_USER"
case "$VISIBLE" in *"$GCN51_DB_NAME"*) ;; *) gcn51_die "$GCN51_DB_NAME not visible to $GCN51_DB_USER";; esac
HAS=$(gcn51_mysql_app -N -B "$GCN51_DB_NAME" -e "SELECT (SELECT COUNT(*) FROM Appointments) + (SELECT COUNT(*) FROM AppointmentPayments) + (SELECT COUNT(*) FROM AppointmentReceipts) + (SELECT COUNT(*) FROM AppointmentOnlinePaymentAttempts) + (SELECT COUNT(*) FROM AppointmentStatusChanges) + (SELECT COUNT(*) FROM AppointmentCancellations) + (SELECT COUNT(*) FROM RefundRecords) + (SELECT COUNT(*) FROM AppointmentPaymentReconciliations);") || gcn51_die "tables not found: apply the migrations first"
[ "$HAS" = "0" ] || gcn51_die "the database already contains $HAS rows; refusing to add to existing data (use a NEW empty database)."
mkdir -p "$FX"; for f in fixtures.json seed-gcn51.sql; do [ -e "$FX/$f" ] && mv "$FX/$f" "$FX/previous-$TS-$f"; done
python3 "$GCN51_DIR/gen_gcn51_fixtures.py" --out-dir "$FX" || gcn51_die "fixture generation failed"
gcn51_seed_is_insert_only "$FX/seed-gcn51.sql" || gcn51_die "seed SQL is not insert-only"
gcn51_sql_is_safe "$FX/seed-gcn51.sql" || gcn51_die "seed SQL contains a forbidden statement"
{
  echo "GCN-51 seed - $(date '+%Y-%m-%d %H:%M:%S')"
  gcn51_mysql_app "$GCN51_DB_NAME" < "$FX/seed-gcn51.sql" || gcn51_die "seeding failed (the file runs in one transaction; check the counts before retrying)"
  EXP_R=$(python3 -c "import json;print(json.load(open('$FX/fixtures.json'))['counts']['receipts'])"); EXP_A=$(python3 -c "import json;print(json.load(open('$FX/fixtures.json'))['counts']['appointments'])"); EXP_P=$(python3 -c "import json;print(json.load(open('$FX/fixtures.json'))['counts']['payments'])")
  GOT_A=$(gcn51_mysql_app -N -B "$GCN51_DB_NAME" -e "SELECT COUNT(*) FROM Appointments;"); GOT_P=$(gcn51_mysql_app -N -B "$GCN51_DB_NAME" -e "SELECT COUNT(*) FROM AppointmentPayments;")
  GOT_R=$(gcn51_mysql_app -N -B "$GCN51_DB_NAME" -e "SELECT COUNT(*) FROM AppointmentReceipts;")
  echo "appointments: $GOT_A (expected $EXP_A)   payments: $GOT_P (expected $EXP_P)   receipts: $GOT_R (expected $EXP_R)"
  [ "$GOT_R" = "$EXP_R" ] || gcn51_die "receipt count differs from the fixtures"
  [ "$GOT_P" = "$EXP_P" ] || gcn51_die "payment count differs from the fixtures"
  [ "$GOT_A" = "$EXP_A" ] || gcn51_die "appointment count differs from the fixtures"
  echo "Seeded. Next: bash $GCN51_DIR/start-gcn51-env.sh --yes   (then gcn51-preflight.sh; no HTTP request is made by any setup script)"
} 2>&1 | tee "$GCN51_DIR/logs/seed-fixtures.log"
