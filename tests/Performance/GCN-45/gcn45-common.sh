#!/usr/bin/env bash
# GCN-45 JMeter helper library. SOURCED by the other scripts, never run directly.
# Holds every fixed target in ONE place so that no script can be pointed at another database, port or process.
#   * Database: only carenova_appointment_gcn45_qa, only on 127.0.0.1:3306, application user only gcn45_qa.
#   * Ports used by this suite: 5235 (doctor stub), 5236 (backend A), 5237 (backend B). Nothing else is ever started or stopped.
#   * Secrets live OUTSIDE every git work tree (your home directory is itself a git repository), in a mode-700 folder.
[ -n "${BASH_VERSION:-}" ] || { echo "run with bash"; return 1 2>/dev/null || exit 1; }

readonly GCN45_DB_NAME="carenova_appointment_gcn45_qa"
readonly GCN45_DB_USER="gcn45_qa"
readonly GCN45_DB_HOST="127.0.0.1"
readonly GCN45_DB_PORT="3306"
readonly GCN45_PORT_STUB=5235 GCN45_PORT_A=5236 GCN45_PORT_B=5237
readonly GCN45_PROTECTED_PORTS="3000 5133 5134 5135 5136 5199"      # GCN-49 backend/stub, Vite, other CareNova services: never touched

readonly GCN45_REPO_API="$HOME/carenova/appointment-integration/src/AppointmentIntegration.Api"
readonly GCN45_REPO_ROOT="$HOME/carenova/appointment-integration"
readonly GCN45_REPORT_DIR="$HOME/carenova/qa-reports/GCN-45/jmeter"
_gcn45_user_dir="$(getconf DARWIN_USER_DIR 2>/dev/null)"; [ -n "$_gcn45_user_dir" ] || _gcn45_user_dir="${TMPDIR:-/tmp}/"
readonly GCN45_SECRET_DIR="${_gcn45_user_dir}carenova-gcn45-secrets"     # random test secrets (mode 700)
readonly GCN45_RUN_DIR="${_gcn45_user_dir}carenova-gcn45-run"            # published backend copy + pid files (mode 700)
readonly GCN45_SECRET_FILE="$GCN45_SECRET_DIR/gcn45-test.env"

gcn45_die() { echo "ERROR: $*" >&2; exit 1; }

# Refuse to use a folder that lies inside any git work tree (secrets must never be committable).
gcn45_assert_outside_git() {
  local d="$1"; while [ ! -d "$d" ] && [ "$d" != "/" ]; do d="$(dirname "$d")"; done
  if git -C "$d" rev-parse --is-inside-work-tree >/dev/null 2>&1; then gcn45_die "$1 is inside a git work tree; refusing to store secrets there."; fi
}

# The database name is a readonly constant; this guard also rejects any override attempt from the environment.
gcn45_assert_db_target() {
  [ "$GCN45_DB_NAME" = "carenova_appointment_gcn45_qa" ] || gcn45_die "database constant was altered"
  [ "$GCN45_DB_USER" = "gcn45_qa" ] || gcn45_die "database user constant was altered"
  [ "$GCN45_DB_HOST" = "127.0.0.1" ] || gcn45_die "only 127.0.0.1 is allowed"
  [ -z "${MYSQL_HOST:-}${MYSQL_TCP_PORT:-}${MYSQL_DATABASE:-}" ] || gcn45_die "unset MYSQL_HOST / MYSQL_TCP_PORT / MYSQL_DATABASE: this suite only talks to $GCN45_DB_HOST:$GCN45_DB_PORT, database $GCN45_DB_NAME"
}

# Administrative connection (database creation only). The password comes from MYSQL_PWD in YOUR terminal and is never stored.
gcn45_mysql_admin() { gcn45_assert_db_target; mysql --protocol=TCP -h "$GCN45_DB_HOST" -P "$GCN45_DB_PORT" -u "${MYSQL_USER:-root}" "$@"; }
# Application connection: the limited user, scoped to the GCN-45 database by name.
gcn45_mysql_app() { gcn45_assert_db_target; MYSQL_PWD="$GCN45_DB_PASSWORD" mysql --protocol=TCP -h "$GCN45_DB_HOST" -P "$GCN45_DB_PORT" -u "$GCN45_DB_USER" "$@"; }

gcn45_load_secrets() {
  gcn45_assert_outside_git "$GCN45_SECRET_DIR"
  [ -f "$GCN45_SECRET_FILE" ] || gcn45_die "no secrets yet. Run: bash $GCN45_REPORT_DIR/gcn45-make-test-secrets.sh"
  [ "$(stat -f '%Lp' "$GCN45_SECRET_FILE")" = "600" ] || gcn45_die "$GCN45_SECRET_FILE must have mode 600"
  set -a; . "$GCN45_SECRET_FILE"; set +a
  [ -n "${GCN45_JWT_SECRET:-}" ] && [ -n "${GCN45_PAYHERE_SECRET:-}" ] && [ -n "${GCN45_DB_PASSWORD:-}" ] || gcn45_die "secrets file incomplete"
}

gcn45_port_in_use() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
gcn45_assert_port_ours() {
  case " $GCN45_PORT_STUB $GCN45_PORT_A $GCN45_PORT_B " in *" $1 "*) ;; *) gcn45_die "port $1 is not one of this suite's ports";; esac
  case " $GCN45_PROTECTED_PORTS " in *" $1 "*) gcn45_die "port $1 is protected";; esac
}

# Static scan of a SQL file: only additive DDL and the EF history insert are acceptable.
# "ON DELETE CASCADE" / "ON UPDATE" in foreign keys are allowed; any other DROP/DELETE/TRUNCATE/UPDATE/GRANT/... is refused.
gcn45_sql_is_safe() {
  local hits
  hits="$(grep -niE '(^|[[:space:]])(DROP|DELETE|TRUNCATE|UPDATE|GRANT|REVOKE|RENAME|CREATE[[:space:]]+(DATABASE|USER|PROCEDURE)|ALTER[[:space:]]+USER|USE)[[:space:]]' "$1" | grep -viE 'ON[[:space:]]+(DELETE|UPDATE)[[:space:]]' || true)"
  if [ -n "$hits" ]; then echo "$hits"; return 1; fi
  return 0
}
