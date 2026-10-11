#!/usr/bin/env bash
# Creates the ISOLATED database carenova_appointment_gcn45_qa and the limited user gcn45_qa (access to that one database only).
#
#   bash gcn45-create-database.sh           shows the plan (password redacted) and exits. Connects to nothing.
#   bash gcn45-create-database.sh --yes     runs it (needs MYSQL_PWD = the MySQL admin password, typed silently in YOUR terminal)
#
#   read -rs "?MySQL root password: " MYSQL_PWD; echo; export MYSQL_PWD
#
# Safety: no DROP, no DELETE, no IF NOT EXISTS (an existing database or user makes it STOP), no other database is read or changed.
# The admin password is never written anywhere. Afterwards it proves the limited user cannot see any other database.
set -u -o pipefail
. "$(dirname "$0")/gcn45-common.sh"
gcn45_assert_db_target
gcn45_load_secrets
LOG="$GCN45_REPORT_DIR/logs/create-database.log"; mkdir -p "$GCN45_REPORT_DIR/logs"

SQL_REDACTED="CREATE DATABASE \`$GCN45_DB_NAME\` CHARACTER SET utf8mb4;
CREATE USER '$GCN45_DB_USER'@'localhost' IDENTIFIED BY '********';
GRANT ALL PRIVILEGES ON \`$GCN45_DB_NAME\`.* TO '$GCN45_DB_USER'@'localhost';"
if [ "${1:-}" != "--yes" ]; then
  echo "PLAN (nothing was executed, no connection was made):"; echo "$SQL_REDACTED"
  echo; echo "Before: existence of the database and the user is checked and the run STOPS if either exists."
  echo "After : the limited user connects and must see ONLY information_schema and $GCN45_DB_NAME."
  echo "Run with --yes to execute (MYSQL_PWD must be set in this terminal)."; exit 0
fi
[ -n "${MYSQL_PWD:-}" ] || gcn45_die "MYSQL_PWD is not set in this terminal (see the comment at the top of this script)."

{
echo "GCN-45 create database - $(date '+%Y-%m-%d %H:%M:%S')   admin user: ${MYSQL_USER:-root}@$GCN45_DB_HOST:$GCN45_DB_PORT"
gcn45_mysql_admin -N -B -e "SELECT 'connected', VERSION();" || gcn45_die "cannot connect (wrong password?)"
DB_EXISTS=$(gcn45_mysql_admin -N -B -e "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='$GCN45_DB_NAME';")
USER_EXISTS=$(gcn45_mysql_admin -N -B -e "SELECT COUNT(*) FROM mysql.user WHERE user='$GCN45_DB_USER';")
echo "database exists: $DB_EXISTS   user exists: $USER_EXISTS"
[ "$DB_EXISTS" = "0" ] || gcn45_die "database $GCN45_DB_NAME already exists. Nothing was changed."
[ "$USER_EXISTS" = "0" ] || gcn45_die "user $GCN45_DB_USER already exists. Nothing was changed."
echo "Executing:"; echo "$SQL_REDACTED"
# the password reaches mysql through stdin only (never in the command line, never logged)
gcn45_mysql_admin <<SQL || gcn45_die "creation failed; check the state with: SHOW DATABASES; and report it, do not retry blindly."
CREATE DATABASE \`$GCN45_DB_NAME\` CHARACTER SET utf8mb4;
CREATE USER '$GCN45_DB_USER'@'localhost' IDENTIFIED BY '$GCN45_DB_PASSWORD';
GRANT ALL PRIVILEGES ON \`$GCN45_DB_NAME\`.* TO '$GCN45_DB_USER'@'localhost';
SQL
echo; echo "Isolation check as $GCN45_DB_USER (databases it can see):"
VISIBLE=$(gcn45_mysql_app -N -B -e "SHOW DATABASES;" | tr '\n' ' ')
echo "  $VISIBLE"
case "$VISIBLE" in *carenova_appointment_qa*|*carenova_appointment_integration*) gcn45_die "ISOLATION FAILED: the limited user can see another CareNova database";; esac
echo "Grants:"; gcn45_mysql_app -N -B -e "SHOW GRANTS FOR CURRENT_USER();" | sed -e "s/IDENTIFIED BY.*//"
echo; echo "Done. Next: bash $GCN45_REPORT_DIR/gcn45-preview-migrations.sh"
} 2>&1 | tee "$LOG"
