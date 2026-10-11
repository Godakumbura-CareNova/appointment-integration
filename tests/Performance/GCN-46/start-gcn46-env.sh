#!/usr/bin/env bash
# Starts the GCN-46 backend on the NEW port 5246 only, against the isolated database as the limited user. No doctor stub, no PayHere (not needed by the read endpoints).
#   bash start-gcn46-env.sh          plan only        bash start-gcn46-env.sh --yes    starts (publishes this branch to the run folder first)
# It NEVER stops or reuses anything: a busy port stops it. Secrets come from the mode-600 secrets file and reach the process through its environment only.
set -u -o pipefail
. "$(dirname "$0")/gcn46-common.sh"
gcn46_assert_db_target; gcn46_assert_port_ours "$GCN46_PORT"
if [ "${1:-}" != "--yes" ]; then echo "PLAN (nothing started): publish $GCN46_REPO_ROOT (current branch, Release) to $GCN46_RUN_DIR/app and start it on http://localhost:$GCN46_PORT. Protected and untouched: ports $GCN46_PROTECTED_PORTS. Use --yes."; exit 0; fi
gcn46_load_secrets; gcn46_assert_outside_git "$GCN46_RUN_DIR"
gcn46_port_in_use "$GCN46_PORT" && gcn46_die "port $GCN46_PORT is already in use; this script never stops anything (use stop-gcn46-env.sh if it is ours)."
gcn46_mysql_app -N -B -e "SELECT 1" "$GCN46_DB_NAME" >/dev/null || gcn46_die "limited user cannot reach $GCN46_DB_NAME"
umask 077; mkdir -p "$GCN46_RUN_DIR" "$GCN46_DIR/logs"; chmod 700 "$GCN46_RUN_DIR"
cd "$GCN46_REPO_ROOT" || exit 1
gcn46_check_branch
dotnet publish src/AppointmentIntegration.Api -c Release -o "$GCN46_RUN_DIR/app" --nologo -v q || gcn46_die "publish failed"
CONN="Server=$GCN46_DB_HOST;Port=$GCN46_DB_PORT;Database=$GCN46_DB_NAME;User=$GCN46_DB_USER;Password=$GCN46_DB_PASSWORD;"
(
  cd "$GCN46_RUN_DIR/app" || exit 1
  export ASPNETCORE_ENVIRONMENT=Staging ASPNETCORE_URLS="http://localhost:$GCN46_PORT"
  export ConnectionStrings__DefaultConnection="$CONN" JwtSettings__Secret="$GCN46_JWT_SECRET"
  nohup dotnet AppointmentIntegration.Api.dll > "$GCN46_DIR/logs/backend.log" 2>&1 &
  echo $! > "$GCN46_RUN_DIR/backend.pid"
)
for _ in $(seq 1 40); do gcn46_port_in_use "$GCN46_PORT" && break; sleep 1; done
echo "backend :$GCN46_PORT -> HTTP $(curl -s -o /dev/null -m 10 -w '%{http_code}' "http://localhost:$GCN46_PORT/api/appointments")  (expect 401: authentication is on)"
echo "Untouched: GCN-45 (5235-5237), GCN-49 (5136, 5199), Vite (3000). Log: $GCN46_DIR/logs/backend.log"
