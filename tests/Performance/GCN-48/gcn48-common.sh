#!/usr/bin/env bash
# GCN-48 JMeter helper library. SOURCED by the other scripts, never run directly.
# One place for every fixed target, so no script can be pointed at another database, port or process.
#   * Database: only carenova_appointment_gcn48_qa on 127.0.0.1:3306, application user only gcn48_qa.
#   * Port used by this suite: 5248 (backend). Nothing else is started or stopped.
#   * Fully separate from GCN-45, GCN-46 and GCN-47: other database/user/ports/secrets/run folder/results; the guards below refuse any GCN-45, GCN-46 or GCN-47 name.
#   * Secrets live OUTSIDE every git work tree (the home directory is itself a git repository) in a mode-700 folder.
[ -n "${BASH_VERSION:-}" ] || { echo "run with bash"; return 1 2>/dev/null || exit 1; }

readonly GCN48_DB_NAME="carenova_appointment_gcn48_qa"
readonly GCN48_DB_USER="gcn48_qa"
readonly GCN48_DB_HOST="127.0.0.1"
readonly GCN48_DB_PORT="3306"
readonly GCN48_PORT=5248
readonly GCN48_PROTECTED_PORTS="3000 5133 5134 5135 5136 5137 5199 5235 5236 5237 5246 5247"   # GCN-49 / GCN-45 / GCN-46 / GCN-47 / Vite / other CareNova services: never touched

# ---- locations: everything is resolved relative to THIS file, nothing is machine specific.
# GCN48_DIR   = this suite folder (tests/Performance/GCN-48); results/, logs/, evidence/ and fixtures/ are written here and are git-ignored.
# GCN48_REPO_ROOT = the repository root (found with git; override with the environment variable of the same name).
GCN48_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Candidates, in order: the environment variable, the git root of this folder (when the suite is shipped inside the repository), and the sibling
# checkout reached relatively from the QA workspace (qa-reports/GCN-48/jmeter -> ../../../appointment-integration).
if [ -z "${GCN48_REPO_ROOT:-}" ]; then
  for _c in "$(git -C "$GCN48_DIR" rev-parse --show-toplevel 2>/dev/null)" "$GCN48_DIR/../../../appointment-integration"; do
    [ -n "$_c" ] && [ -d "$_c/src/AppointmentIntegration.Api" ] && { GCN48_REPO_ROOT="$(cd "$_c" && pwd)"; break; }
  done
fi
GCN48_REPO_ROOT="${GCN48_REPO_ROOT:-}"
[ -n "$GCN48_REPO_ROOT" ] && [ -d "$GCN48_REPO_ROOT/src/AppointmentIntegration.Api" ] || { echo "ERROR: cannot find the repository root (src/AppointmentIntegration.Api). Set GCN48_REPO_ROOT." >&2; exit 1; }
GCN48_REPO_API="$GCN48_REPO_ROOT/src/AppointmentIntegration.Api"
readonly GCN48_DIR GCN48_REPO_ROOT GCN48_REPO_API
# Optional guard: set GCN48_EXPECTED_BRANCH (for example feature/GCN-48-appointment-cancellation) to refuse to run on any other branch.
GCN48_EXPECTED_BRANCH="${GCN48_EXPECTED_BRANCH:-}"

# ---- private folders for secrets and the published backend. Defaults: macOS per-user temp folder, else XDG_RUNTIME_DIR, else TMPDIR.
# Override with GCN48_SECRETS_DIR / GCN48_RUN_DIR. They must NOT be inside a git work tree (checked) and are created with mode 700.
_gcn48_private_base() {
  local d; d="$(getconf DARWIN_USER_DIR 2>/dev/null)"
  if [ -n "$d" ]; then printf '%s' "$d"; elif [ -n "${XDG_RUNTIME_DIR:-}" ]; then printf '%s/' "${XDG_RUNTIME_DIR%/}"; else printf '%s/' "${TMPDIR:-/tmp}"; fi
}
_gcn48_base="$(_gcn48_private_base)"
readonly GCN48_SECRET_DIR="${GCN48_SECRETS_DIR:-${_gcn48_base}carenova-gcn48-secrets}"   # random test secrets (mode 700)
readonly GCN48_RUN_DIR="${GCN48_RUN_DIR:-${_gcn48_base}carenova-gcn48-run}"              # published backend copy + pid files (mode 700)
readonly GCN48_SECRET_FILE="$GCN48_SECRET_DIR/gcn48-test.env"

# Portable file mode (GNU stat -c, BSD/macOS stat -f).
gcn48_mode() { stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1"; }
# Refuse to run on an unexpected branch, when GCN48_EXPECTED_BRANCH is set.
gcn48_check_branch() {
  local b; b="$(git -C "$GCN48_REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)"
  if [ -n "$GCN48_EXPECTED_BRANCH" ] && [ "$b" != "$GCN48_EXPECTED_BRANCH" ]; then gcn48_die "the repository is on '$b', expected '$GCN48_EXPECTED_BRANCH' (GCN48_EXPECTED_BRANCH)"; fi
  echo "repository branch: ${b:-unknown}"
}

gcn48_die() { echo "ERROR: $*" >&2; exit 1; }

# Refuse to store secrets inside any git work tree.
gcn48_assert_outside_git() {
  local d="$1"; while [ ! -d "$d" ] && [ "$d" != "/" ]; do d="$(dirname "$d")"; done
  if git -C "$d" rev-parse --is-inside-work-tree >/dev/null 2>&1; then gcn48_die "$1 is inside a git work tree; refusing to store secrets there."; fi
}

# The target is a set of readonly constants; this guard also rejects overrides from the environment and any GCN-45 / GCN-46 / GCN-47 / shared name.
gcn48_assert_db_target() {
  [ "$GCN48_DB_NAME" = "carenova_appointment_gcn48_qa" ] || gcn48_die "database constant was altered"
  [ "$GCN48_DB_USER" = "gcn48_qa" ] || gcn48_die "database user constant was altered"
  [ "$GCN48_DB_HOST" = "127.0.0.1" ] || gcn48_die "only 127.0.0.1 is allowed"
  case "$GCN48_DB_NAME$GCN48_DB_USER$GCN48_SECRET_DIR$GCN48_RUN_DIR" in *gcn45*|*gcn46*|*gcn47*|*carenova_appointment_qa*|*carenova_appointment_integration*) gcn48_die "a GCN-45, GCN-46, GCN-47 or shared name leaked into the GCN-48 constants";; esac
  [ -z "${MYSQL_HOST:-}${MYSQL_TCP_PORT:-}${MYSQL_DATABASE:-}" ] || gcn48_die "unset MYSQL_HOST / MYSQL_TCP_PORT / MYSQL_DATABASE: this suite only talks to $GCN48_DB_HOST:$GCN48_DB_PORT, database $GCN48_DB_NAME"
}

# Administrative connection (database creation only). The password comes from MYSQL_PWD in YOUR terminal and is never stored.
gcn48_mysql_admin() { gcn48_assert_db_target; mysql --protocol=TCP -h "$GCN48_DB_HOST" -P "$GCN48_DB_PORT" -u "${MYSQL_USER:-root}" "$@"; }
# Application connection: the limited user.
gcn48_mysql_app() { gcn48_assert_db_target; MYSQL_PWD="$GCN48_DB_PASSWORD" mysql --protocol=TCP -h "$GCN48_DB_HOST" -P "$GCN48_DB_PORT" -u "$GCN48_DB_USER" "$@"; }

gcn48_load_secrets() {
  gcn48_assert_outside_git "$GCN48_SECRET_DIR"
  [ -f "$GCN48_SECRET_FILE" ] || gcn48_die "no secrets yet. Run: bash $GCN48_DIR/gcn48-make-test-secrets.sh"
  [ "$(gcn48_mode "$GCN48_SECRET_FILE")" = "600" ] || gcn48_die "$GCN48_SECRET_FILE must have mode 600"
  set -a; . "$GCN48_SECRET_FILE"; set +a
  [ -n "${GCN48_JWT_SECRET:-}" ] && [ -n "${GCN48_DB_PASSWORD:-}" ] || gcn48_die "secrets file incomplete"
}

gcn48_port_in_use() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
gcn48_assert_port_ours() {
  [ "$1" = "$GCN48_PORT" ] || gcn48_die "port $1 is not this suite's port ($GCN48_PORT)"
  case " $GCN48_PROTECTED_PORTS " in *" $1 "*) gcn48_die "port $1 is protected";; esac
}

# Static scan of a SQL file: only additive DDL / INSERT is acceptable. ON DELETE / ON UPDATE inside foreign keys are allowed.
gcn48_sql_is_safe() {
  local hits
  hits="$(grep -niE '(^|[[:space:]])(DROP|DELETE|TRUNCATE|UPDATE|GRANT|REVOKE|RENAME|CREATE[[:space:]]+(DATABASE|USER|PROCEDURE)|ALTER[[:space:]]+USER|USE)[[:space:]]' "$1" | grep -viE 'ON[[:space:]]+(DELETE|UPDATE)[[:space:]]' || true)"
  if [ -n "$hits" ]; then echo "$hits"; return 1; fi
  return 0
}
# The seed file may contain ONLY inserts into the two synthetic-data tables plus transaction control.
gcn48_seed_is_insert_only() {
  local bad
  bad="$(grep -vE '^[[:space:]]*$|^[[:space:]]*--|^(START TRANSACTION|COMMIT);$|^INSERT INTO `(Appointments|AppointmentPayments)` ' "$1" | head -5 || true)"
  if [ -n "$bad" ]; then echo "$bad"; return 1; fi
  return 0
}
