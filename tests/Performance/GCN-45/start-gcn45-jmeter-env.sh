#!/usr/bin/env bash
# Starts the GCN-45 JMeter environment on NEW ports only:
#   doctor stub :5235   backend A :5236 (PayHere TEST config)   backend B :5237 (PayHere NOT configured, for the gateway-unavailable check)
# Both backends use the isolated database carenova_appointment_gcn45_qa as the limited user gcn45_qa.
#   bash start-gcn45-jmeter-env.sh          plan only
#   bash start-gcn45-jmeter-env.sh --yes    starts (publishes a copy of the backend to the run folder first)
# It NEVER stops, restarts or reuses anything: if a port is busy it stops with a message. Secrets are read from the mode-600 secrets file
# and handed to the processes through their environment only (not on a command line, not in a file in any repository).
set -u -o pipefail
. "$(dirname "$0")/gcn45-common.sh"
gcn45_assert_db_target
for p in $GCN45_PORT_STUB $GCN45_PORT_A $GCN45_PORT_B; do gcn45_assert_port_ours "$p"; done
if [ "${1:-}" != "--yes" ]; then
  echo "PLAN (nothing started): publish backend (Release) to $GCN45_RUN_DIR/app; start doctor stub :$GCN45_PORT_STUB, backend A :$GCN45_PORT_A, backend B :$GCN45_PORT_B"
  echo "Protected and untouched: ports $GCN45_PROTECTED_PORTS. Use --yes."; exit 0
fi
gcn45_load_secrets; gcn45_assert_outside_git "$GCN45_RUN_DIR"
for p in $GCN45_PORT_STUB $GCN45_PORT_A $GCN45_PORT_B; do gcn45_port_in_use "$p" && gcn45_die "port $p is already in use; this script never stops anything. Run stop-gcn45-jmeter-env.sh if it is ours."; done
gcn45_mysql_app -N -B -e "SELECT 1" "$GCN45_DB_NAME" >/dev/null || gcn45_die "limited user cannot reach $GCN45_DB_NAME (run create-database and apply-migrations first)"
umask 077; mkdir -p "$GCN45_RUN_DIR" "$GCN45_REPORT_DIR/logs"; chmod 700 "$GCN45_RUN_DIR"
cd "$GCN45_REPO_ROOT" || exit 1
git rev-parse --abbrev-ref HEAD | grep -qx "feature/GCN-45-appointment-payment" || gcn45_die "repository is not on feature/GCN-45-appointment-payment"
dotnet publish src/AppointmentIntegration.Api -c Release -o "$GCN45_RUN_DIR/app" --nologo -v q || gcn45_die "publish failed"

nohup python3 "$GCN45_REPORT_DIR/gcn45-doctor-stub.py" "$GCN45_PORT_STUB" > "$GCN45_REPORT_DIR/logs/doctor-stub.log" 2>&1 &
echo $! > "$GCN45_RUN_DIR/stub.pid"

CONN="Server=$GCN45_DB_HOST;Port=$GCN45_DB_PORT;Database=$GCN45_DB_NAME;User=$GCN45_DB_USER;Password=$GCN45_DB_PASSWORD;"
start_backend() {  # $1 name  $2 port  $3 PayHere merchant secret ("" = not configured)
  # Settings are exported INSIDE a subshell (never passed as `env VAR=value` arguments, so no secret appears in a process argument list).
  (
    cd "$GCN45_RUN_DIR/app" || exit 1
    export ASPNETCORE_ENVIRONMENT=Staging ASPNETCORE_URLS="http://localhost:$2"
    export ConnectionStrings__DefaultConnection="$CONN" JwtSettings__Secret="$GCN45_JWT_SECRET"
    export DoctorPaymentService__BaseUrl="http://localhost:$GCN45_PORT_STUB"
    export PayHere__MerchantId="$GCN45_PAYHERE_MERCHANT_ID" PayHere__MerchantSecret="$3" PayHere__Sandbox=true PayHere__AllowLivePayments=false
    export PayHere__NotifyUrl="http://localhost:$GCN45_PORT_A/api/appointment-payments/payhere/notify" PayHere__FrontendBaseUrl="http://localhost:3000"
    nohup dotnet AppointmentIntegration.Api.dll > "$GCN45_REPORT_DIR/logs/backend-$1.log" 2>&1 &
    echo $! > "$GCN45_RUN_DIR/backend-$1.pid"
  )
}
start_backend A "$GCN45_PORT_A" "$GCN45_PAYHERE_SECRET"
start_backend B "$GCN45_PORT_B" ""

for port in $GCN45_PORT_STUB $GCN45_PORT_A $GCN45_PORT_B; do
  for _ in $(seq 1 40); do gcn45_port_in_use "$port" && break; sleep 1; done
done
echo "doctor stub  :$GCN45_PORT_STUB -> HTTP $(curl -s -o /dev/null -m 5 -w '%{http_code}' "http://127.0.0.1:$GCN45_PORT_STUB/__stats")  (expect 200)"
echo "backend A    :$GCN45_PORT_A -> HTTP $(curl -s -o /dev/null -m 10 -w '%{http_code}' "http://localhost:$GCN45_PORT_A/api/appointments/1/payment")  (expect 401: authentication is on)"
echo "backend B    :$GCN45_PORT_B -> HTTP $(curl -s -o /dev/null -m 10 -w '%{http_code}' "http://localhost:$GCN45_PORT_B/api/appointments/1/payment")  (expect 401)"
echo "Untouched: 5136 (GCN-49 backend), 5199 (GCN-49 stub), 3000 (Vite). Logs: $GCN45_REPORT_DIR/logs/"
