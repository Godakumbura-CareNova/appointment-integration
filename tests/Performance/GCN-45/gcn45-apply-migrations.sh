#!/usr/bin/env bash
# Applies the REVIEWED preview script to carenova_appointment_gcn45_qa ONLY, as the limited user gcn45_qa.
#   bash gcn45-apply-migrations.sh          plan only (connects to nothing)
#   bash gcn45-apply-migrations.sh --yes    applies
# Safety: the target database is a constant and is passed to mysql by name; the limited user cannot reach any other database;
# the script is re-scanned for forbidden statements; the database must contain NO tables yet (otherwise it stops).
set -u -o pipefail
. "$(dirname "$0")/gcn45-common.sh"
gcn45_assert_db_target; gcn45_load_secrets
F="$GCN45_REPORT_DIR/gcn45-migrations-preview.sql"; LOG="$GCN45_REPORT_DIR/logs/apply-migrations.log"
[ -f "$F" ] || gcn45_die "no preview file. Run gcn45-preview-migrations.sh first and review it."
gcn45_sql_is_safe "$F" || gcn45_die "forbidden statement in $F"
if [ "${1:-}" != "--yes" ]; then echo "PLAN: run $F against $GCN45_DB_NAME on $GCN45_DB_HOST:$GCN45_DB_PORT as $GCN45_DB_USER. Nothing executed. Use --yes."; exit 0; fi
{
echo "GCN-45 apply migrations - $(date '+%Y-%m-%d %H:%M:%S')"
VISIBLE=$(gcn45_mysql_app -N -B -e "SHOW DATABASES;" | tr '\n' ' ') || gcn45_die "cannot connect as $GCN45_DB_USER (was the database created?)"
case "$VISIBLE" in *"$GCN45_DB_NAME"*) ;; *) gcn45_die "$GCN45_DB_NAME not visible to $GCN45_DB_USER";; esac
TABLES=$(gcn45_mysql_app -N -B -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$GCN45_DB_NAME';")
echo "tables before: $TABLES"; [ "$TABLES" = "0" ] || gcn45_die "the database is not empty; refusing to apply."
gcn45_mysql_app "$GCN45_DB_NAME" < "$F" || gcn45_die "applying failed (the script runs in transactions; inspect before retrying)"
echo "tables after:"; gcn45_mysql_app -t "$GCN45_DB_NAME" -e "SELECT table_name AS tbl FROM information_schema.tables WHERE table_schema='$GCN45_DB_NAME' ORDER BY 1;"
echo "migration history:"; gcn45_mysql_app -t "$GCN45_DB_NAME" -e "SELECT MigrationId FROM __EFMigrationsHistory ORDER BY 1;"
} 2>&1 | tee "$LOG"
