#!/usr/bin/env bash
# GCN-53 JMeter helper library. SOURCED by the other scripts, never run directly.
# One place for every fixed target, so no script can be pointed at another database, port or process.
#   * Database: only carenova_appointment_gcn53_qa on 127.0.0.1:3306, application user only gcn53_qa.
#   * Port used by this suite: 5253 (backend). Nothing else is started or stopped.
#   * Fully separate from GCN-45, GCN-46, GCN-47, GCN-48 and GCN-51: other database/user/ports/secrets/run folder/results; the guards below refuse any GCN-45, GCN-46, GCN-47, GCN-48 or GCN-51 name.
#   * Secrets live OUTSIDE every git work tree (the home directory is itself a git repository) in a mode-700 folder.
[ -n "${BASH_VERSION:-}" ] || { echo "run with bash"; return 1 2>/dev/null || exit 1; }

readonly GCN53_DB_NAME="carenova_appointment_gcn53_qa"
readonly GCN53_DB_USER="gcn53_qa"
readonly GCN53_DB_HOST="127.0.0.1"
readonly GCN53_DB_PORT="3306"
readonly GCN53_PORT=5253
readonly GCN53_PROTECTED_PORTS="3000 5133 5134 5135 5136 5137 5199 5235 5236 5237 5246 5247 5248 5251"   # GCN-49 / GCN-45 / GCN-46 / GCN-47 / GCN-48 / GCN-51 / Vite / other CareNova services: never touched

# ---- locations: everything is resolved relative to THIS file, nothing is machine specific.
# GCN53_DIR   = this suite folder (tests/Performance/GCN-53): source files only.
# GCN53_OUT   = where every GENERATED file goes (fixtures, results, logs, evidence): OUTSIDE the repository, default ~/carenova/qa-reports/GCN-53/jmeter (override with GCN53_OUT_DIR).
# GCN53_REPO_ROOT = the repository root (found with git; override with the environment variable of the same name).
GCN53_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Candidates, in order: the environment variable, the git root of this folder (when the suite is shipped inside the repository), and the sibling
# checkout reached relatively from the QA workspace (qa-reports/GCN-53/jmeter -> ../../../appointment-integration).
if [ -z "${GCN53_REPO_ROOT:-}" ]; then
  for _c in "$(git -C "$GCN53_DIR" rev-parse --show-toplevel 2>/dev/null)" "$GCN53_DIR/../../../appointment-integration"; do
    [ -n "$_c" ] && [ -d "$_c/src/AppointmentIntegration.Api" ] && { GCN53_REPO_ROOT="$(cd "$_c" && pwd)"; break; }
  done
fi
GCN53_REPO_ROOT="${GCN53_REPO_ROOT:-}"
[ -n "$GCN53_REPO_ROOT" ] && [ -d "$GCN53_REPO_ROOT/src/AppointmentIntegration.Api" ] || { echo "ERROR: cannot find the repository root (src/AppointmentIntegration.Api). Set GCN53_REPO_ROOT." >&2; exit 1; }
GCN53_REPO_API="$GCN53_REPO_ROOT/src/AppointmentIntegration.Api"
GCN53_OUT="${GCN53_OUT_DIR:-$HOME/carenova/qa-reports/GCN-53/jmeter}"
case "$GCN53_OUT" in "$GCN53_REPO_ROOT"*) echo "ERROR: the output folder must be outside the repository: $GCN53_OUT" >&2; exit 1;; esac
case "$GCN53_OUT" in *gcn45*|*gcn46*|*gcn47*|*gcn48*|*gcn51*|*GCN-45*|*GCN-46*|*GCN-47*|*GCN-48*|*GCN-51*) echo "ERROR: the output folder names another ticket: $GCN53_OUT" >&2; exit 1;; esac
export GCN53_OUT
readonly GCN53_DIR GCN53_REPO_ROOT GCN53_REPO_API GCN53_OUT
# Optional guard: set GCN53_EXPECTED_BRANCH (for example feature/GCN-53-admin-dashboard) to refuse to run on any other branch.
GCN53_EXPECTED_BRANCH="${GCN53_EXPECTED_BRANCH:-}"

# ---- private folders for secrets and the published backend. Defaults: macOS per-user temp folder, else XDG_RUNTIME_DIR, else TMPDIR.
# Override with GCN53_SECRETS_DIR / GCN53_RUN_DIR. They must NOT be inside a git work tree (checked) and are created with mode 700.
_gcn53_private_base() {
  local d; d="$(getconf DARWIN_USER_DIR 2>/dev/null)"
  if [ -n "$d" ]; then printf '%s' "$d"; elif [ -n "${XDG_RUNTIME_DIR:-}" ]; then printf '%s/' "${XDG_RUNTIME_DIR%/}"; else printf '%s/' "${TMPDIR:-/tmp}"; fi
}
_gcn53_base="$(_gcn53_private_base)"
readonly GCN53_SECRET_DIR="${GCN53_SECRETS_DIR:-${_gcn53_base}carenova-gcn53-secrets}"   # random test secrets (mode 700)
readonly GCN53_RUN_DIR="${GCN53_RUN_DIR:-${_gcn53_base}carenova-gcn53-run}"              # published backend copy + pid files (mode 700)
readonly GCN53_SECRET_FILE="$GCN53_SECRET_DIR/gcn53-test.env"

# Portable file mode (GNU stat -c, BSD/macOS stat -f).
gcn53_mode() { stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1"; }
# Refuse to run on an unexpected branch, when GCN53_EXPECTED_BRANCH is set.
gcn53_check_branch() {
  local b; b="$(git -C "$GCN53_REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)"
  if [ -n "$GCN53_EXPECTED_BRANCH" ] && [ "$b" != "$GCN53_EXPECTED_BRANCH" ]; then gcn53_die "the repository is on '$b', expected '$GCN53_EXPECTED_BRANCH' (GCN53_EXPECTED_BRANCH)"; fi
  echo "repository branch: ${b:-unknown}"
}

gcn53_die() { echo "ERROR: $*" >&2; exit 1; }

# Refuse to store secrets inside any git work tree.
gcn53_assert_outside_git() {
  local d="$1"; while [ ! -d "$d" ] && [ "$d" != "/" ]; do d="$(dirname "$d")"; done
  if git -C "$d" rev-parse --is-inside-work-tree >/dev/null 2>&1; then gcn53_die "$1 is inside a git work tree; refusing to store secrets there."; fi
}

# The target is a set of readonly constants; this guard also rejects overrides from the environment and any GCN-45 / GCN-46 / GCN-47 / GCN-48 / GCN-51 / shared name.
gcn53_assert_db_target() {
  [ "$GCN53_DB_NAME" = "carenova_appointment_gcn53_qa" ] || gcn53_die "database constant was altered"
  [ "$GCN53_DB_USER" = "gcn53_qa" ] || gcn53_die "database user constant was altered"
  [ "$GCN53_DB_HOST" = "127.0.0.1" ] || gcn53_die "only 127.0.0.1 is allowed"
  case "$GCN53_DB_NAME$GCN53_DB_USER$GCN53_SECRET_DIR$GCN53_RUN_DIR" in *gcn45*|*gcn46*|*gcn47*|*gcn48*|*gcn51*|*carenova_appointment_qa*|*carenova_appointment_integration*) gcn53_die "a GCN-45, GCN-46, GCN-47, GCN-48, GCN-51 or shared name leaked into the GCN-53 constants";; esac
  [ -z "${MYSQL_HOST:-}${MYSQL_TCP_PORT:-}${MYSQL_DATABASE:-}" ] || gcn53_die "unset MYSQL_HOST / MYSQL_TCP_PORT / MYSQL_DATABASE: this suite only talks to $GCN53_DB_HOST:$GCN53_DB_PORT, database $GCN53_DB_NAME"
}

# Administrative connection (database creation only). The password comes from MYSQL_PWD in YOUR terminal and is never stored.
gcn53_mysql_admin() { gcn53_assert_db_target; mysql --protocol=TCP -h "$GCN53_DB_HOST" -P "$GCN53_DB_PORT" -u "${MYSQL_USER:-root}" "$@"; }
# Application connection: the limited user.
gcn53_mysql_app() { gcn53_assert_db_target; MYSQL_PWD="$GCN53_DB_PASSWORD" mysql --protocol=TCP -h "$GCN53_DB_HOST" -P "$GCN53_DB_PORT" -u "$GCN53_DB_USER" "$@"; }

gcn53_load_secrets() {
  gcn53_assert_outside_git "$GCN53_SECRET_DIR"
  [ -f "$GCN53_SECRET_FILE" ] || gcn53_die "no secrets yet. Run: bash $GCN53_DIR/gcn53-make-test-secrets.sh"
  [ "$(gcn53_mode "$GCN53_SECRET_FILE")" = "600" ] || gcn53_die "$GCN53_SECRET_FILE must have mode 600"
  set -a; . "$GCN53_SECRET_FILE"; set +a
  [ -n "${GCN53_JWT_SECRET:-}" ] && [ -n "${GCN53_DB_PASSWORD:-}" ] || gcn53_die "secrets file incomplete"
}

gcn53_port_in_use() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
gcn53_assert_port_ours() {
  [ "$1" = "$GCN53_PORT" ] || gcn53_die "port $1 is not this suite's port ($GCN53_PORT)"
  case " $GCN53_PROTECTED_PORTS " in *" $1 "*) gcn53_die "port $1 is protected";; esac
}

# Static scan of a SQL file: only additive DDL / INSERT is acceptable. ON DELETE / ON UPDATE inside foreign keys are allowed.
gcn53_sql_is_safe() {
  local hits
  hits="$(grep -niE '(^|[[:space:]])(DROP|DELETE|TRUNCATE|UPDATE|GRANT|REVOKE|RENAME|CREATE[[:space:]]+(DATABASE|USER|PROCEDURE)|ALTER[[:space:]]+USER|USE)[[:space:]]' "$1" | grep -viE 'ON[[:space:]]+(DELETE|UPDATE)[[:space:]]' || true)"
  if [ -n "$hits" ]; then echo "$hits"; return 1; fi
  return 0
}
# The seed file may contain ONLY inserts into the three synthetic-data tables (Appointments, AppointmentPayments, AppointmentReceipts) plus transaction control.
gcn53_seed_is_insert_only() {
  local bad
  bad="$(grep -vE '^[[:space:]]*$|^[[:space:]]*--|^(START TRANSACTION|COMMIT);$|^INSERT INTO `(Appointments|AppointmentPayments|AppointmentReceipts)` ' "$1" | head -5 || true)"
  if [ -n "$bad" ]; then echo "$bad"; return 1; fi
  return 0
}
