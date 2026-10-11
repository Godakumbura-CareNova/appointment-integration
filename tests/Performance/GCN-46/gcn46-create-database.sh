#!/usr/bin/env bash
# Creates the ISOLATED database carenova_appointment_gcn46_qa and the limited user gcn46_qa (access to that one database only).
#   bash gcn46-create-database.sh           shows the plan (password redacted) and exits. Connects to nothing.
#   bash gcn46-create-database.sh --yes     runs it (MYSQL_PWD = the MySQL admin password typed silently in YOUR terminal)
#   read -rs "?MySQL root password: " MYSQL_PWD; echo; export MYSQL_PWD
# Safety: no DROP, no DELETE, no IF NOT EXISTS (an existing database or user makes it STOP); no other database is read or changed.
# Afterwards it proves the limited user cannot see any other CareNova database (including the GCN-45 and shared QA ones).
set -u -o pipefail
. "$(dirname "$0")/gcn46-common.sh"
gcn46_assert_db_target; gcn46_load_secrets
LOG="$GCN46_DIR/logs/create-database.log"; mkdir -p "$GCN46_DIR/logs"
SQL_REDACTED="CREATE DATABASE \`$GCN46_DB_NAME\` CHARACTER SET utf8mb4;
CREATE USER '$GCN46_DB_USER'@'localhost' IDENTIFIED BY '********';
GRANT ALL PRIVILEGES ON \`$GCN46_DB_NAME\`.* TO '$GCN46_DB_USER'@'localhost';"
if [ "${1:-}" != "--yes" ]; then
  echo "PLAN (nothing was executed, no connection was made):"; echo "$SQL_REDACTED"
  echo; echo "Before: existence of the database and the user is checked; the run STOPS if either exists."
  echo "After : the limited user must see ONLY information_schema and $GCN46_DB_NAME."; echo "Use --yes (MYSQL_PWD must be set in this terminal)."; exit 0
fi
[ -n "${MYSQL_PWD:-}" ] || gcn46_die "MYSQL_PWD is not set in this terminal."
{
echo "GCN-46 create database - $(date '+%Y-%m-%d %H:%M:%S')   admin user: ${MYSQL_USER:-root}@$GCN46_DB_HOST:$GCN46_DB_PORT"
gcn46_mysql_admin -N -B -e "SELECT 'connected', VERSION();" || gcn46_die "cannot connect (wrong password?)"
DB_EXISTS=$(gcn46_mysql_admin -N -B -e "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='$GCN46_DB_NAME';")
USER_EXISTS=$(gcn46_mysql_admin -N -B -e "SELECT COUNT(*) FROM mysql.user WHERE user='$GCN46_DB_USER';")
echo "database exists: $DB_EXISTS   user exists: $USER_EXISTS"
[ "$DB_EXISTS" = "0" ] || gcn46_die "database $GCN46_DB_NAME already exists. Nothing was changed."
[ "$USER_EXISTS" = "0" ] || gcn46_die "user $GCN46_DB_USER already exists. Nothing was changed."
echo "Executing:"; echo "$SQL_REDACTED"
gcn46_mysql_admin <<SQL || gcn46_die "creation failed; check SHOW DATABASES; and report it, do not retry blindly."
CREATE DATABASE \`$GCN46_DB_NAME\` CHARACTER SET utf8mb4;
CREATE USER '$GCN46_DB_USER'@'localhost' IDENTIFIED BY '$GCN46_DB_PASSWORD';
GRANT ALL PRIVILEGES ON \`$GCN46_DB_NAME\`.* TO '$GCN46_DB_USER'@'localhost';
SQL
echo; echo "Isolation check as $GCN46_DB_USER (databases it can see):"
VISIBLE=$(gcn46_mysql_app -N -B -e "SHOW DATABASES;" | tr '\n' ' '); echo "  $VISIBLE"
case "$VISIBLE" in *carenova_appointment_qa*|*carenova_appointment_integration*|*gcn45*) gcn46_die "ISOLATION FAILED: the limited user can see another CareNova database";; esac
echo "Grants:"; gcn46_mysql_app -N -B -e "SHOW GRANTS FOR CURRENT_USER();" | sed -e "s/IDENTIFIED BY.*//"
echo; echo "Done. Next: bash $GCN46_DIR/gcn46-preview-migrations.sh"
} 2>&1 | tee "$LOG"
