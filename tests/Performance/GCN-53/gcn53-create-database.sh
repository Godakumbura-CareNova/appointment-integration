#!/usr/bin/env bash
# Creates the ISOLATED database carenova_appointment_gcn53_qa and the limited user gcn53_qa (access to that one database only).
#   bash gcn53-create-database.sh           shows the plan (password redacted) and exits. Connects to nothing.
#   bash gcn53-create-database.sh --yes     runs it (MYSQL_PWD = the MySQL admin password typed silently in YOUR terminal)
#   read -rs "?MySQL root password: " MYSQL_PWD; echo; export MYSQL_PWD
# Safety: no DROP, no DELETE, no IF NOT EXISTS (an existing database or user makes it STOP); no other database is read or changed.
# Afterwards it proves the limited user cannot see any other CareNova database (including the GCN-45, GCN-46, GCN-47, GCN-48 and shared QA ones).
set -u -o pipefail
. "$(dirname "$0")/gcn53-common.sh"
gcn53_assert_db_target; gcn53_load_secrets
LOG="$GCN53_OUT/logs/create-database.log"; mkdir -p "$GCN53_OUT/logs"
SQL_REDACTED="CREATE DATABASE \`$GCN53_DB_NAME\` CHARACTER SET utf8mb4;
CREATE USER '$GCN53_DB_USER'@'localhost' IDENTIFIED BY '********';
GRANT ALL PRIVILEGES ON \`$GCN53_DB_NAME\`.* TO '$GCN53_DB_USER'@'localhost';"
if [ "${1:-}" != "--yes" ]; then
  echo "PLAN (nothing was executed, no connection was made):"; echo "$SQL_REDACTED"
  echo; echo "Before: existence of the database and the user is checked; the run STOPS if either exists."
  echo "After : the limited user must see ONLY information_schema and $GCN53_DB_NAME."; echo "Use --yes (MYSQL_PWD must be set in this terminal)."; exit 0
fi
[ -n "${MYSQL_PWD:-}" ] || gcn53_die "MYSQL_PWD is not set in this terminal."
{
echo "GCN-53 create database - $(date '+%Y-%m-%d %H:%M:%S')   admin user: ${MYSQL_USER:-root}@$GCN53_DB_HOST:$GCN53_DB_PORT"
gcn53_mysql_admin -N -B -e "SELECT 'connected', VERSION();" || gcn53_die "cannot connect (wrong password?)"
DB_EXISTS=$(gcn53_mysql_admin -N -B -e "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='$GCN53_DB_NAME';")
USER_EXISTS=$(gcn53_mysql_admin -N -B -e "SELECT COUNT(*) FROM mysql.user WHERE user='$GCN53_DB_USER';")
echo "database exists: $DB_EXISTS   user exists: $USER_EXISTS"
[ "$DB_EXISTS" = "0" ] || gcn53_die "database $GCN53_DB_NAME already exists. Nothing was changed."
[ "$USER_EXISTS" = "0" ] || gcn53_die "user $GCN53_DB_USER already exists. Nothing was changed."
echo "Executing:"; echo "$SQL_REDACTED"
gcn53_mysql_admin <<SQL || gcn53_die "creation failed; check SHOW DATABASES; and report it, do not retry blindly."
CREATE DATABASE \`$GCN53_DB_NAME\` CHARACTER SET utf8mb4;
CREATE USER '$GCN53_DB_USER'@'localhost' IDENTIFIED BY '$GCN53_DB_PASSWORD';
GRANT ALL PRIVILEGES ON \`$GCN53_DB_NAME\`.* TO '$GCN53_DB_USER'@'localhost';
SQL
echo; echo "Isolation check as $GCN53_DB_USER (databases it can see):"
VISIBLE=$(gcn53_mysql_app -N -B -e "SHOW DATABASES;" | tr '\n' ' '); echo "  $VISIBLE"
case "$VISIBLE" in *carenova_appointment_qa*|*carenova_appointment_integration*|*gcn45*|*gcn46*|*gcn47*|*gcn48*) gcn53_die "ISOLATION FAILED: the limited user can see another CareNova database";; esac
echo "Grants:"; gcn53_mysql_app -N -B -e "SHOW GRANTS FOR CURRENT_USER();" | sed -e "s/IDENTIFIED BY.*//"
echo; echo "Done. Next: bash $GCN53_DIR/gcn53-preview-migrations.sh"
} 2>&1 | tee "$LOG"
