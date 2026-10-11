#!/usr/bin/env bash
# Starts the GCN-47 backend on the NEW port 5247 only, against the isolated database as the limited user. No doctor stub, no PayHere (not needed by the read endpoints).
#   bash start-gcn47-env.sh          plan only        bash start-gcn47-env.sh --yes    starts (publishes this branch to the run folder first)
# It NEVER stops or reuses anything: a busy port stops it. Secrets come from the mode-600 secrets file and reach the process through its environment only.
set -u -o pipefail
. "$(dirname "$0")/gcn47-common.sh"
gcn47_assert_db_target; gcn47_assert_port_ours "$GCN47_PORT"
if [ "${1:-}" != "--yes" ]; then echo "PLAN (nothing started): publish $GCN47_REPO_ROOT (current branch, Release) to $GCN47_RUN_DIR/app and start it on http://localhost:$GCN47_PORT. Protected and untouched: ports $GCN47_PROTECTED_PORTS. Use --yes."; exit 0; fi
gcn47_load_secrets; gcn47_assert_outside_git "$GCN47_RUN_DIR"
gcn47_port_in_use "$GCN47_PORT" && gcn47_die "port $GCN47_PORT is already in use; this script never stops anything (use stop-gcn47-env.sh if it is ours)."
gcn47_mysql_app -N -B -e "SELECT 1" "$GCN47_DB_NAME" >/dev/null || gcn47_die "limited user cannot reach $GCN47_DB_NAME"
umask 077; mkdir -p "$GCN47_RUN_DIR" "$GCN47_DIR/logs"; chmod 700 "$GCN47_RUN_DIR"
cd "$GCN47_REPO_ROOT" || exit 1
gcn47_check_branch
dotnet publish src/AppointmentIntegration.Api -c Release -o "$GCN47_RUN_DIR/app" --nologo -v q || gcn47_die "publish failed"
CONN="Server=$GCN47_DB_HOST;Port=$GCN47_DB_PORT;Database=$GCN47_DB_NAME;User=$GCN47_DB_USER;Password=$GCN47_DB_PASSWORD;"
(
  cd "$GCN47_RUN_DIR/app" || exit 1
  export ASPNETCORE_ENVIRONMENT=Staging ASPNETCORE_URLS="http://localhost:$GCN47_PORT"
  export ConnectionStrings__DefaultConnection="$CONN" JwtSettings__Secret="$GCN47_JWT_SECRET"
    # one "Request starting" log line per request (command-line option on the dotnet command below): the post-run check counts them to prove that exactly five requests reached the server
    # the patient-contact service is intentionally NOT configured (UserAuthService:BaseUrl empty): contacts come back as unavailable, the documented fallback
    export UserAuthService__BaseUrl=""
  nohup dotnet AppointmentIntegration.Api.dll --Logging:LogLevel:Microsoft.AspNetCore.Hosting.Diagnostics=Information > "$GCN47_DIR/logs/backend.log" 2>&1 &
  echo $! > "$GCN47_RUN_DIR/backend.pid"
)
for _ in $(seq 1 60); do gcn47_port_in_use "$GCN47_PORT" && break; sleep 1; done
# NO health check over HTTP: the suite sends exactly five requests in total. Readiness is the listening socket only (lsof), never a request.
if gcn47_port_in_use "$GCN47_PORT"; then echo "backend listening on :$GCN47_PORT (checked with lsof, no HTTP request was sent)"; else gcn47_die "the backend did not start; see $GCN47_DIR/logs/backend.log"; fi
echo "Untouched: GCN-45 (5235-5237), GCN-46 (5246), GCN-49 (5136, 5199), Vite (3000). Log: $GCN47_DIR/logs/backend.log"
