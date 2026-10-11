#!/usr/bin/env bash
# Applies the REVIEWED preview script to carenova_appointment_gcn46_qa ONLY, as the limited user gcn46_qa.
#   bash gcn46-apply-migrations.sh          plan only        bash gcn46-apply-migrations.sh --yes    applies
# Safety: the target is a constant passed to mysql by name; the limited user cannot reach another database; the script is re-scanned;
# the database must contain NO tables yet (otherwise it stops).
set -u -o pipefail
. "$(dirname "$0")/gcn46-common.sh"
gcn46_assert_db_target; gcn46_load_secrets
F="$GCN46_DIR/gcn46-migrations-preview.sql"; LOG="$GCN46_DIR/logs/apply-migrations.log"
[ -f "$F" ] || gcn46_die "no preview file. Run gcn46-preview-migrations.sh first and review it."
gcn46_sql_is_safe "$F" || gcn46_die "forbidden statement in $F"
if [ "${1:-}" != "--yes" ]; then echo "PLAN: run $F against $GCN46_DB_NAME on $GCN46_DB_HOST:$GCN46_DB_PORT as $GCN46_DB_USER. Nothing executed. Use --yes."; exit 0; fi
{
echo "GCN-46 apply migrations - $(date '+%Y-%m-%d %H:%M:%S')"
VISIBLE=$(gcn46_mysql_app -N -B -e "SHOW DATABASES;" | tr '\n' ' ') || gcn46_die "cannot connect as $GCN46_DB_USER (was the database created?)"
case "$VISIBLE" in *"$GCN46_DB_NAME"*) ;; *) gcn46_die "$GCN46_DB_NAME not visible to $GCN46_DB_USER";; esac
TABLES=$(gcn46_mysql_app -N -B -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$GCN46_DB_NAME';")
echo "tables before: $TABLES"; [ "$TABLES" = "0" ] || gcn46_die "the database is not empty; refusing to apply."
gcn46_mysql_app "$GCN46_DB_NAME" < "$F" || gcn46_die "applying failed (the script runs in transactions; inspect before retrying)"
echo "tables after:"; gcn46_mysql_app -t "$GCN46_DB_NAME" -e "SELECT table_name AS tbl FROM information_schema.tables WHERE table_schema='$GCN46_DB_NAME' ORDER BY 1;"
echo "migration history:"; gcn46_mysql_app -t "$GCN46_DB_NAME" -e "SELECT MigrationId FROM __EFMigrationsHistory ORDER BY 1;"
} 2>&1 | tee "$LOG"
