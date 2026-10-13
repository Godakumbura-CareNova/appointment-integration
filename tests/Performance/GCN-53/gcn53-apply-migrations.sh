#!/usr/bin/env bash
# Applies the REVIEWED preview script to carenova_appointment_gcn53_qa ONLY, as the limited user gcn53_qa.
#   bash gcn53-apply-migrations.sh          plan only        bash gcn53-apply-migrations.sh --yes    applies
# Safety: the target is a constant passed to mysql by name; the limited user cannot reach another database; the script is re-scanned;
# the database must contain NO tables yet (otherwise it stops).
set -u -o pipefail
. "$(dirname "$0")/gcn53-common.sh"
gcn53_assert_db_target; gcn53_load_secrets
F="$GCN53_OUT/gcn53-migrations-preview.sql"; LOG="$GCN53_OUT/logs/apply-migrations.log"
[ -f "$F" ] || gcn53_die "no preview file. Run gcn53-preview-migrations.sh first and review it."
gcn53_sql_is_safe "$F" || gcn53_die "forbidden statement in $F"
if [ "${1:-}" != "--yes" ]; then echo "PLAN: run $F against $GCN53_DB_NAME on $GCN53_DB_HOST:$GCN53_DB_PORT as $GCN53_DB_USER. Nothing executed. Use --yes."; exit 0; fi
{
echo "GCN-53 apply migrations - $(date '+%Y-%m-%d %H:%M:%S')"
VISIBLE=$(gcn53_mysql_app -N -B -e "SHOW DATABASES;" | tr '\n' ' ') || gcn53_die "cannot connect as $GCN53_DB_USER (was the database created?)"
case "$VISIBLE" in *"$GCN53_DB_NAME"*) ;; *) gcn53_die "$GCN53_DB_NAME not visible to $GCN53_DB_USER";; esac
TABLES=$(gcn53_mysql_app -N -B -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$GCN53_DB_NAME';")
echo "tables before: $TABLES"; [ "$TABLES" = "0" ] || gcn53_die "the database is not empty; refusing to apply."
gcn53_mysql_app "$GCN53_DB_NAME" < "$F" || gcn53_die "applying failed (the script runs in transactions; inspect before retrying)"
echo "tables after:"; gcn53_mysql_app -t "$GCN53_DB_NAME" -e "SELECT table_name AS tbl FROM information_schema.tables WHERE table_schema='$GCN53_DB_NAME' ORDER BY 1;"
echo "migration history:"; gcn53_mysql_app -t "$GCN53_DB_NAME" -e "SELECT MigrationId FROM __EFMigrationsHistory ORDER BY 1;"
} 2>&1 | tee "$LOG"
