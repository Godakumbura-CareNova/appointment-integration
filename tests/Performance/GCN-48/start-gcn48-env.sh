#!/usr/bin/env bash
# Starts the GCN-48 backend on the NEW port 5248 only, against the isolated database as the limited user. No doctor stub, no PayHere (not needed by the read endpoints).
#   bash start-gcn48-env.sh          plan only        bash start-gcn48-env.sh --yes    starts (publishes this branch to the run folder first)
# It NEVER stops or reuses anything: a busy port stops it. Secrets come from the mode-600 secrets file and reach the process through its environment only.
set -u -o pipefail
. "$(dirname "$0")/gcn48-common.sh"
gcn48_assert_db_target; gcn48_assert_port_ours "$GCN48_PORT"
if [ "${1:-}" != "--yes" ]; then echo "PLAN (nothing started): publish $GCN48_REPO_ROOT (current branch, Release) to $GCN48_RUN_DIR/app and start it on http://localhost:$GCN48_PORT. Protected and untouched: ports $GCN48_PROTECTED_PORTS. Use --yes."; exit 0; fi
gcn48_load_secrets; gcn48_assert_outside_git "$GCN48_RUN_DIR"
gcn48_port_in_use "$GCN48_PORT" && gcn48_die "port $GCN48_PORT is already in use; this script never stops anything (use stop-gcn48-env.sh if it is ours)."
gcn48_mysql_app -N -B -e "SELECT 1" "$GCN48_DB_NAME" >/dev/null || gcn48_die "limited user cannot reach $GCN48_DB_NAME"
umask 077; mkdir -p "$GCN48_RUN_DIR" "$GCN48_DIR/logs"; chmod 700 "$GCN48_RUN_DIR"
cd "$GCN48_REPO_ROOT" || exit 1
gcn48_check_branch
dotnet publish src/AppointmentIntegration.Api -c Release -o "$GCN48_RUN_DIR/app" --nologo -v q || gcn48_die "publish failed"
CONN="Server=$GCN48_DB_HOST;Port=$GCN48_DB_PORT;Database=$GCN48_DB_NAME;User=$GCN48_DB_USER;Password=$GCN48_DB_PASSWORD;"
(
  cd "$GCN48_RUN_DIR/app" || exit 1
  export ASPNETCORE_ENVIRONMENT=Staging ASPNETCORE_URLS="http://localhost:$GCN48_PORT"
  export ConnectionStrings__DefaultConnection="$CONN" JwtSettings__Secret="$GCN48_JWT_SECRET"
    # one "Request starting" log line per request (command-line option on the dotnet command below): the post-run check counts them to prove that exactly five requests reached the server
    # the patient-contact service is intentionally NOT configured (UserAuthService:BaseUrl empty): contacts come back as unavailable, the documented fallback
    export UserAuthService__BaseUrl=""
  nohup dotnet AppointmentIntegration.Api.dll --Logging:LogLevel:Microsoft.AspNetCore.Hosting.Diagnostics=Information > "$GCN48_DIR/logs/backend.log" 2>&1 &
  echo $! > "$GCN48_RUN_DIR/backend.pid"
)
for _ in $(seq 1 60); do gcn48_port_in_use "$GCN48_PORT" && break; sleep 1; done
# NO health check over HTTP: the suite sends exactly five requests in total. Readiness is the listening socket only (lsof), never a request.
if gcn48_port_in_use "$GCN48_PORT"; then echo "backend listening on :$GCN48_PORT (checked with lsof, no HTTP request was sent)"; else gcn48_die "the backend did not start; see $GCN48_DIR/logs/backend.log"; fi
echo "Untouched: GCN-45 (5235-5237), GCN-46 (5246), GCN-49 (5136, 5199), Vite (3000). Log: $GCN48_DIR/logs/backend.log"
