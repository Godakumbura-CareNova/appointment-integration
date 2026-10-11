#!/usr/bin/env bash
# GCN-46 JMeter helper library. SOURCED by the other scripts, never run directly.
# One place for every fixed target, so no script can be pointed at another database, port or process.
#   * Database: only carenova_appointment_gcn46_qa on 127.0.0.1:3306, application user only gcn46_qa.
#   * Port used by this suite: 5246 (backend). Nothing else is started or stopped.
#   * Fully separate from GCN-45: other database/user/ports/secrets/run folder/results; the guards below refuse any GCN-45 name.
#   * Secrets live OUTSIDE every git work tree (the home directory is itself a git repository) in a mode-700 folder.
[ -n "${BASH_VERSION:-}" ] || { echo "run with bash"; return 1 2>/dev/null || exit 1; }

readonly GCN46_DB_NAME="carenova_appointment_gcn46_qa"
readonly GCN46_DB_USER="gcn46_qa"
readonly GCN46_DB_HOST="127.0.0.1"
readonly GCN46_DB_PORT="3306"
readonly GCN46_PORT=5246
readonly GCN46_PROTECTED_PORTS="3000 5133 5134 5135 5136 5137 5199 5235 5236 5237"   # GCN-49 / GCN-45 / Vite / other CareNova services: never touched

# ---- locations: everything is resolved relative to THIS file, nothing is machine specific.
# GCN46_DIR   = this suite folder (tests/Performance/GCN-46); results/, logs/, evidence/ and fixtures/ are written here and are git-ignored.
# GCN46_REPO_ROOT = the repository root (found with git; override with the environment variable of the same name).
GCN46_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GCN46_REPO_ROOT="${GCN46_REPO_ROOT:-$(git -C "$GCN46_DIR" rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$GCN46_REPO_ROOT" ] && [ -d "$GCN46_REPO_ROOT/src/AppointmentIntegration.Api" ] || { echo "ERROR: cannot find the repository root (src/AppointmentIntegration.Api). Set GCN46_REPO_ROOT." >&2; exit 1; }
GCN46_REPO_API="$GCN46_REPO_ROOT/src/AppointmentIntegration.Api"
readonly GCN46_DIR GCN46_REPO_ROOT GCN46_REPO_API
# Optional guard: set GCN46_EXPECTED_BRANCH (for example feature/GCN-46-patient-appointments) to refuse to run on any other branch.
GCN46_EXPECTED_BRANCH="${GCN46_EXPECTED_BRANCH:-}"

# ---- private folders for secrets and the published backend. Defaults: macOS per-user temp folder, else XDG_RUNTIME_DIR, else TMPDIR.
# Override with GCN46_SECRETS_DIR / GCN46_RUN_DIR. They must NOT be inside a git work tree (checked) and are created with mode 700.
_gcn46_private_base() {
  local d; d="$(getconf DARWIN_USER_DIR 2>/dev/null)"
  if [ -n "$d" ]; then printf '%s' "$d"; elif [ -n "${XDG_RUNTIME_DIR:-}" ]; then printf '%s/' "${XDG_RUNTIME_DIR%/}"; else printf '%s/' "${TMPDIR:-/tmp}"; fi
}
_gcn46_base="$(_gcn46_private_base)"
readonly GCN46_SECRET_DIR="${GCN46_SECRETS_DIR:-${_gcn46_base}carenova-gcn46-secrets}"   # random test secrets (mode 700)
readonly GCN46_RUN_DIR="${GCN46_RUN_DIR:-${_gcn46_base}carenova-gcn46-run}"              # published backend copy + pid files (mode 700)
readonly GCN46_SECRET_FILE="$GCN46_SECRET_DIR/gcn46-test.env"

# Portable file mode (GNU stat -c, BSD/macOS stat -f).
gcn46_mode() { stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1"; }
# Refuse to run on an unexpected branch, when GCN46_EXPECTED_BRANCH is set.
gcn46_check_branch() {
  local b; b="$(git -C "$GCN46_REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)"
  if [ -n "$GCN46_EXPECTED_BRANCH" ] && [ "$b" != "$GCN46_EXPECTED_BRANCH" ]; then gcn46_die "the repository is on '$b', expected '$GCN46_EXPECTED_BRANCH' (GCN46_EXPECTED_BRANCH)"; fi
  echo "repository branch: ${b:-unknown}"
}

gcn46_die() { echo "ERROR: $*" >&2; exit 1; }

# Refuse to store secrets inside any git work tree.
gcn46_assert_outside_git() {
  local d="$1"; while [ ! -d "$d" ] && [ "$d" != "/" ]; do d="$(dirname "$d")"; done
  if git -C "$d" rev-parse --is-inside-work-tree >/dev/null 2>&1; then gcn46_die "$1 is inside a git work tree; refusing to store secrets there."; fi
}

# The target is a set of readonly constants; this guard also rejects overrides from the environment and any GCN-45 / shared name.
gcn46_assert_db_target() {
  [ "$GCN46_DB_NAME" = "carenova_appointment_gcn46_qa" ] || gcn46_die "database constant was altered"
  [ "$GCN46_DB_USER" = "gcn46_qa" ] || gcn46_die "database user constant was altered"
  [ "$GCN46_DB_HOST" = "127.0.0.1" ] || gcn46_die "only 127.0.0.1 is allowed"
  case "$GCN46_DB_NAME$GCN46_DB_USER$GCN46_SECRET_DIR$GCN46_RUN_DIR" in *gcn45*|*carenova_appointment_qa*|*carenova_appointment_integration*) gcn46_die "a GCN-45 or shared name leaked into the GCN-46 constants";; esac
  [ -z "${MYSQL_HOST:-}${MYSQL_TCP_PORT:-}${MYSQL_DATABASE:-}" ] || gcn46_die "unset MYSQL_HOST / MYSQL_TCP_PORT / MYSQL_DATABASE: this suite only talks to $GCN46_DB_HOST:$GCN46_DB_PORT, database $GCN46_DB_NAME"
}

# Administrative connection (database creation only). The password comes from MYSQL_PWD in YOUR terminal and is never stored.
gcn46_mysql_admin() { gcn46_assert_db_target; mysql --protocol=TCP -h "$GCN46_DB_HOST" -P "$GCN46_DB_PORT" -u "${MYSQL_USER:-root}" "$@"; }
# Application connection: the limited user.
gcn46_mysql_app() { gcn46_assert_db_target; MYSQL_PWD="$GCN46_DB_PASSWORD" mysql --protocol=TCP -h "$GCN46_DB_HOST" -P "$GCN46_DB_PORT" -u "$GCN46_DB_USER" "$@"; }

gcn46_load_secrets() {
  gcn46_assert_outside_git "$GCN46_SECRET_DIR"
  [ -f "$GCN46_SECRET_FILE" ] || gcn46_die "no secrets yet. Run: bash $GCN46_DIR/gcn46-make-test-secrets.sh"
  [ "$(gcn46_mode "$GCN46_SECRET_FILE")" = "600" ] || gcn46_die "$GCN46_SECRET_FILE must have mode 600"
  set -a; . "$GCN46_SECRET_FILE"; set +a
  [ -n "${GCN46_JWT_SECRET:-}" ] && [ -n "${GCN46_DB_PASSWORD:-}" ] || gcn46_die "secrets file incomplete"
}

gcn46_port_in_use() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
gcn46_assert_port_ours() {
  [ "$1" = "$GCN46_PORT" ] || gcn46_die "port $1 is not this suite's port ($GCN46_PORT)"
  case " $GCN46_PROTECTED_PORTS " in *" $1 "*) gcn46_die "port $1 is protected";; esac
}

# Static scan of a SQL file: only additive DDL / INSERT is acceptable. ON DELETE / ON UPDATE inside foreign keys are allowed.
gcn46_sql_is_safe() {
  local hits
  hits="$(grep -niE '(^|[[:space:]])(DROP|DELETE|TRUNCATE|UPDATE|GRANT|REVOKE|RENAME|CREATE[[:space:]]+(DATABASE|USER|PROCEDURE)|ALTER[[:space:]]+USER|USE)[[:space:]]' "$1" | grep -viE 'ON[[:space:]]+(DELETE|UPDATE)[[:space:]]' || true)"
  if [ -n "$hits" ]; then echo "$hits"; return 1; fi
  return 0
}
# The seed file may contain ONLY inserts into the two synthetic-data tables plus transaction control.
gcn46_seed_is_insert_only() {
  local bad
  bad="$(grep -vE '^[[:space:]]*$|^[[:space:]]*--|^(START TRANSACTION|COMMIT);$|^INSERT INTO `(Appointments|AppointmentPayments)` ' "$1" | head -5 || true)"
  if [ -n "$bad" ]; then echo "$bad"; return 1; fi
  return 0
}
