#!/usr/bin/env bash
# Applies the REVIEWED preview script to carenova_appointment_gcn51_qa ONLY, as the limited user gcn51_qa.
#   bash gcn51-apply-migrations.sh          plan only        bash gcn51-apply-migrations.sh --yes    applies
# Safety: the target is a constant passed to mysql by name; the limited user cannot reach another database; the script is re-scanned;
# the database must contain NO tables yet (otherwise it stops).
set -u -o pipefail
. "$(dirname "$0")/gcn51-common.sh"
gcn51_assert_db_target; gcn51_load_secrets
F="$GCN51_DIR/gcn51-migrations-preview.sql"; LOG="$GCN51_DIR/logs/apply-migrations.log"
[ -f "$F" ] || gcn51_die "no preview file. Run gcn51-preview-migrations.sh first and review it."
gcn51_sql_is_safe "$F" || gcn51_die "forbidden statement in $F"
if [ "${1:-}" != "--yes" ]; then echo "PLAN: run $F against $GCN51_DB_NAME on $GCN51_DB_HOST:$GCN51_DB_PORT as $GCN51_DB_USER. Nothing executed. Use --yes."; exit 0; fi
{
echo "GCN-51 apply migrations - $(date '+%Y-%m-%d %H:%M:%S')"
VISIBLE=$(gcn51_mysql_app -N -B -e "SHOW DATABASES;" | tr '\n' ' ') || gcn51_die "cannot connect as $GCN51_DB_USER (was the database created?)"
case "$VISIBLE" in *"$GCN51_DB_NAME"*) ;; *) gcn51_die "$GCN51_DB_NAME not visible to $GCN51_DB_USER";; esac
TABLES=$(gcn51_mysql_app -N -B -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$GCN51_DB_NAME';")
echo "tables before: $TABLES"; [ "$TABLES" = "0" ] || gcn51_die "the database is not empty; refusing to apply."
gcn51_mysql_app "$GCN51_DB_NAME" < "$F" || gcn51_die "applying failed (the script runs in transactions; inspect before retrying)"
echo "tables after:"; gcn51_mysql_app -t "$GCN51_DB_NAME" -e "SELECT table_name AS tbl FROM information_schema.tables WHERE table_schema='$GCN51_DB_NAME' ORDER BY 1;"
echo "migration history:"; gcn51_mysql_app -t "$GCN51_DB_NAME" -e "SELECT MigrationId FROM __EFMigrationsHistory ORDER BY 1;"
} 2>&1 | tee "$LOG"
