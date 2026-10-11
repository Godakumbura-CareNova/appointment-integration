#!/usr/bin/env bash
# Applies the REVIEWED preview script to carenova_appointment_gcn47_qa ONLY, as the limited user gcn47_qa.
#   bash gcn47-apply-migrations.sh          plan only        bash gcn47-apply-migrations.sh --yes    applies
# Safety: the target is a constant passed to mysql by name; the limited user cannot reach another database; the script is re-scanned;
# the database must contain NO tables yet (otherwise it stops).
set -u -o pipefail
. "$(dirname "$0")/gcn47-common.sh"
gcn47_assert_db_target; gcn47_load_secrets
F="$GCN47_DIR/gcn47-migrations-preview.sql"; LOG="$GCN47_DIR/logs/apply-migrations.log"
[ -f "$F" ] || gcn47_die "no preview file. Run gcn47-preview-migrations.sh first and review it."
gcn47_sql_is_safe "$F" || gcn47_die "forbidden statement in $F"
if [ "${1:-}" != "--yes" ]; then echo "PLAN: run $F against $GCN47_DB_NAME on $GCN47_DB_HOST:$GCN47_DB_PORT as $GCN47_DB_USER. Nothing executed. Use --yes."; exit 0; fi
{
echo "GCN-47 apply migrations - $(date '+%Y-%m-%d %H:%M:%S')"
VISIBLE=$(gcn47_mysql_app -N -B -e "SHOW DATABASES;" | tr '\n' ' ') || gcn47_die "cannot connect as $GCN47_DB_USER (was the database created?)"
case "$VISIBLE" in *"$GCN47_DB_NAME"*) ;; *) gcn47_die "$GCN47_DB_NAME not visible to $GCN47_DB_USER";; esac
TABLES=$(gcn47_mysql_app -N -B -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$GCN47_DB_NAME';")
echo "tables before: $TABLES"; [ "$TABLES" = "0" ] || gcn47_die "the database is not empty; refusing to apply."
gcn47_mysql_app "$GCN47_DB_NAME" < "$F" || gcn47_die "applying failed (the script runs in transactions; inspect before retrying)"
echo "tables after:"; gcn47_mysql_app -t "$GCN47_DB_NAME" -e "SELECT table_name AS tbl FROM information_schema.tables WHERE table_schema='$GCN47_DB_NAME' ORDER BY 1;"
echo "migration history:"; gcn47_mysql_app -t "$GCN47_DB_NAME" -e "SELECT MigrationId FROM __EFMigrationsHistory ORDER BY 1;"
} 2>&1 | tee "$LOG"
