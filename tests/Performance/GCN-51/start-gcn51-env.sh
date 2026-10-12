#!/usr/bin/env bash
# Starts the GCN-51 backend on the NEW port 5251 only, against the isolated database as the limited user. No doctor stub, no PayHere (not needed by the read-only dashboard endpoints).
#   bash start-gcn51-env.sh          plan only        bash start-gcn51-env.sh --yes    starts (publishes this branch to the run folder first)
# It NEVER stops or reuses anything: a busy port stops it. Secrets come from the mode-600 secrets file and reach the process through its environment only.
set -u -o pipefail
. "$(dirname "$0")/gcn51-common.sh"
gcn51_assert_db_target; gcn51_assert_port_ours "$GCN51_PORT"
if [ "${1:-}" != "--yes" ]; then echo "PLAN (nothing started): publish $GCN51_REPO_ROOT (current branch, Release) to $GCN51_RUN_DIR/app and start it on http://localhost:$GCN51_PORT. Protected and untouched: ports $GCN51_PROTECTED_PORTS. Use --yes."; exit 0; fi
gcn51_load_secrets; gcn51_assert_outside_git "$GCN51_RUN_DIR"
gcn51_port_in_use "$GCN51_PORT" && gcn51_die "port $GCN51_PORT is already in use; this script never stops anything (use stop-gcn51-env.sh if it is ours)."
gcn51_mysql_app -N -B -e "SELECT 1" "$GCN51_DB_NAME" >/dev/null || gcn51_die "limited user cannot reach $GCN51_DB_NAME"
umask 077; mkdir -p "$GCN51_RUN_DIR" "$GCN51_DIR/logs"; chmod 700 "$GCN51_RUN_DIR"
cd "$GCN51_REPO_ROOT" || exit 1
gcn51_check_branch
dotnet publish src/AppointmentIntegration.Api -c Release -o "$GCN51_RUN_DIR/app" --nologo -v q || gcn51_die "publish failed"
CONN="Server=$GCN51_DB_HOST;Port=$GCN51_DB_PORT;Database=$GCN51_DB_NAME;User=$GCN51_DB_USER;Password=$GCN51_DB_PASSWORD;"
(
  cd "$GCN51_RUN_DIR/app" || exit 1
  export ASPNETCORE_ENVIRONMENT=Staging ASPNETCORE_URLS="http://localhost:$GCN51_PORT"
  export ConnectionStrings__DefaultConnection="$CONN" JwtSettings__Secret="$GCN51_JWT_SECRET"
    # one "Request starting" log line per request (command-line option on the dotnet command below): the post-run check counts them to prove that exactly five requests reached the server
    # the patient-contact service is intentionally NOT configured (UserAuthService:BaseUrl empty): contacts come back as unavailable, the documented fallback
    export UserAuthService__BaseUrl=""
  nohup dotnet AppointmentIntegration.Api.dll --Logging:LogLevel:Microsoft.AspNetCore.Hosting.Diagnostics=Information > "$GCN51_DIR/logs/backend.log" 2>&1 &
  echo $! > "$GCN51_RUN_DIR/backend.pid"
)
for _ in $(seq 1 60); do gcn51_port_in_use "$GCN51_PORT" && break; sleep 1; done
# NO health check over HTTP: the suite sends exactly the 38 planned requests in total. Readiness is the listening socket only (lsof), never a request.
if gcn51_port_in_use "$GCN51_PORT"; then echo "backend listening on :$GCN51_PORT (checked with lsof, no HTTP request was sent)"; else gcn51_die "the backend did not start; see $GCN51_DIR/logs/backend.log"; fi
echo "Untouched: GCN-45 (5235-5237), GCN-46 (5246), GCN-47 (5247), GCN-48 (5248), GCN-49 (5136, 5199), Vite (3000). Log: $GCN51_DIR/logs/backend.log"
