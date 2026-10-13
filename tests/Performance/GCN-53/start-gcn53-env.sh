#!/usr/bin/env bash
# Starts the GCN-53 backend on the NEW port 5253 only, against the isolated database as the limited user. No doctor stub, no PayHere (not needed by the read-only dashboard endpoints).
#   bash start-gcn53-env.sh          plan only        bash start-gcn53-env.sh --yes    starts (publishes this branch to the run folder first)
# It NEVER stops or reuses anything: a busy port stops it. Secrets come from the mode-600 secrets file and reach the process through its environment only.
set -u -o pipefail
. "$(dirname "$0")/gcn53-common.sh"
gcn53_assert_db_target; gcn53_assert_port_ours "$GCN53_PORT"
if [ "${1:-}" != "--yes" ]; then echo "PLAN (nothing started): publish $GCN53_REPO_ROOT (current branch, Release) to $GCN53_RUN_DIR/app and start it on http://localhost:$GCN53_PORT. Protected and untouched: ports $GCN53_PROTECTED_PORTS. Use --yes."; exit 0; fi
gcn53_load_secrets; gcn53_assert_outside_git "$GCN53_RUN_DIR"
gcn53_port_in_use "$GCN53_PORT" && gcn53_die "port $GCN53_PORT is already in use; this script never stops anything (use stop-gcn53-env.sh if it is ours)."
gcn53_mysql_app -N -B -e "SELECT 1" "$GCN53_DB_NAME" >/dev/null || gcn53_die "limited user cannot reach $GCN53_DB_NAME"
umask 077; mkdir -p "$GCN53_RUN_DIR" "$GCN53_OUT/logs"; chmod 700 "$GCN53_RUN_DIR"
cd "$GCN53_REPO_ROOT" || exit 1
gcn53_check_branch
dotnet publish src/AppointmentIntegration.Api -c Release -o "$GCN53_RUN_DIR/app" --nologo -v q || gcn53_die "publish failed"
CONN="Server=$GCN53_DB_HOST;Port=$GCN53_DB_PORT;Database=$GCN53_DB_NAME;User=$GCN53_DB_USER;Password=$GCN53_DB_PASSWORD;"
(
  cd "$GCN53_RUN_DIR/app" || exit 1
  export ASPNETCORE_ENVIRONMENT=Staging ASPNETCORE_URLS="http://localhost:$GCN53_PORT"
  export ConnectionStrings__DefaultConnection="$CONN" JwtSettings__Secret="$GCN53_JWT_SECRET"
    # one "Request starting" log line per request (command-line option on the dotnet command below): the post-run check counts them to prove that exactly five requests reached the server
    # the patient-contact service is intentionally NOT configured (UserAuthService:BaseUrl empty): contacts come back as unavailable, the documented fallback
    export UserAuthService__BaseUrl=""
  nohup dotnet AppointmentIntegration.Api.dll --Logging:LogLevel:Microsoft.AspNetCore.Hosting.Diagnostics=Information > "$GCN53_OUT/logs/backend.log" 2>&1 &
  echo $! > "$GCN53_RUN_DIR/backend.pid"
)
for _ in $(seq 1 60); do gcn53_port_in_use "$GCN53_PORT" && break; sleep 1; done
# NO health check over HTTP: the suite sends exactly the 66 planned requests in total. Readiness is the listening socket only (lsof), never a request.
if gcn53_port_in_use "$GCN53_PORT"; then echo "backend listening on :$GCN53_PORT (checked with lsof, no HTTP request was sent)"; else gcn53_die "the backend did not start; see $GCN53_OUT/logs/backend.log"; fi
echo "Untouched: GCN-45 (5235-5237), GCN-46 (5246), GCN-47 (5247), GCN-48 (5248), GCN-49 (5136, 5199), Vite (3000). Log: $GCN53_OUT/logs/backend.log"
