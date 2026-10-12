#!/usr/bin/env bash
# Applies the REVIEWED preview script to carenova_appointment_gcn48_qa ONLY, as the limited user gcn48_qa.
#   bash gcn48-apply-migrations.sh          plan only        bash gcn48-apply-migrations.sh --yes    applies
# Safety: the target is a constant passed to mysql by name; the limited user cannot reach another database; the script is re-scanned;
# the database must contain NO tables yet (otherwise it stops).
set -u -o pipefail
. "$(dirname "$0")/gcn48-common.sh"
gcn48_assert_db_target; gcn48_load_secrets
F="$GCN48_DIR/gcn48-migrations-preview.sql"; LOG="$GCN48_DIR/logs/apply-migrations.log"
[ -f "$F" ] || gcn48_die "no preview file. Run gcn48-preview-migrations.sh first and review it."
gcn48_sql_is_safe "$F" || gcn48_die "forbidden statement in $F"
if [ "${1:-}" != "--yes" ]; then echo "PLAN: run $F against $GCN48_DB_NAME on $GCN48_DB_HOST:$GCN48_DB_PORT as $GCN48_DB_USER. Nothing executed. Use --yes."; exit 0; fi
{
echo "GCN-48 apply migrations - $(date '+%Y-%m-%d %H:%M:%S')"
VISIBLE=$(gcn48_mysql_app -N -B -e "SHOW DATABASES;" | tr '\n' ' ') || gcn48_die "cannot connect as $GCN48_DB_USER (was the database created?)"
case "$VISIBLE" in *"$GCN48_DB_NAME"*) ;; *) gcn48_die "$GCN48_DB_NAME not visible to $GCN48_DB_USER";; esac
TABLES=$(gcn48_mysql_app -N -B -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$GCN48_DB_NAME';")
echo "tables before: $TABLES"; [ "$TABLES" = "0" ] || gcn48_die "the database is not empty; refusing to apply."
gcn48_mysql_app "$GCN48_DB_NAME" < "$F" || gcn48_die "applying failed (the script runs in transactions; inspect before retrying)"
echo "tables after:"; gcn48_mysql_app -t "$GCN48_DB_NAME" -e "SELECT table_name AS tbl FROM information_schema.tables WHERE table_schema='$GCN48_DB_NAME' ORDER BY 1;"
echo "migration history:"; gcn48_mysql_app -t "$GCN48_DB_NAME" -e "SELECT MigrationId FROM __EFMigrationsHistory ORDER BY 1;"
} 2>&1 | tee "$LOG"
