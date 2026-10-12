#!/usr/bin/env bash
# Runs the GCN-51 plan ONCE: 9 scenarios J01..J09 (exactly 9 HTTP samplers, one per scenario; 38 requests in total because J09 loops its sampler 30 times), all read-only GET requests, then the read-only verification.
#   bash run-gcn51-jmeter.sh           plan only: sends and changes nothing
#   bash run-gcn51-jmeter.sh --yes     runs  (pre-flight -> JMeter -> database unchanged check -> server request count -> summary)
# The requests are read-only and safe to repeat; the database must be IDENTICAL after the run (proved by read-only SQL). Tokens are minted inside JMeter from GCN51_JWT_SECRET, which reaches ONLY the JMeter process.
# No retries (httpclient4.retrycount=0), no redirects. Functional, response-time and repeated-request stability check on one thread: NOT a load or concurrency test.
set -u -o pipefail
. "$(dirname "$0")/gcn51-common.sh"
JMX="$GCN51_DIR/GCN51RoleDashboardTest.jmx"; FIX="$GCN51_DIR/fixtures/fixtures.json"; R="$GCN51_DIR/results/run"; TS="$(date +%Y%m%d-%H%M%S)"
if [ "${1:-}" != "--yes" ]; then
  echo "PLAN (nothing sent, nothing changed): pre-flight (no HTTP), then JMeter sends 38 read-only GET requests (9 scenarios, 9 samplers) to localhost:$GCN51_PORT:"
  echo "  J01 GET /api/patient/dashboard/appointments                 Patient 1  -> 200 contract"
  echo "  J02 GET /api/patient/dashboard/appointments                 Patient 1  -> 200 counts, preview, payment-status counts = fixtures"
  echo "  J03 GET /api/staff/dashboard/appointment-payments           Staff      -> 200 contract"
  echo "  J04 GET /api/staff/dashboard/appointment-payments           Staff      -> 200 pending transfers, recent payments, income = fixtures"
  echo "  J05 GET /api/doctor/appointments                            Doctor 1   -> 200 statistics and list = fixtures (no doctor DASHBOARD endpoint exists)"
  echo "  J06 GET /api/staff/dashboard/appointment-payments           no token   -> 401, empty body"
  echo "  J07 GET /api/staff/dashboard/appointment-payments           Patient    -> 403"
  echo "  J08 GET /api/patient/dashboard/appointments                 Staff      -> 403"
  echo "  J09 ONE sampler looped 30 x: GET staff payments dashboard   Staff      -> 200 each, values stable, response times within the documented thresholds"
  echo "Add --yes to run. Needs a freshly seeded database (see README)."; exit 0
fi
[ -f "$JMX" ] && [ -f "$FIX" ] || gcn51_die "plan or fixtures missing (generate and seed first)"
command -v jmeter >/dev/null || gcn51_die "jmeter not found"
gcn51_load_secrets
bash "$GCN51_DIR/gcn51-preflight.sh" > /dev/null || { cat "$GCN51_DIR/evidence/preflight.txt"; gcn51_die "pre-flight failed: nothing was sent"; }
[ -e "$R" ] && { mv "$R" "$GCN51_DIR/results/run-previous-$TS"; echo "previous results kept in results/run-previous-$TS"; }
mkdir -p "$R"; rm -f "$GCN51_DIR/evidence/jm05-response.json"
export JVM_ARGS="-Xms128m -Xmx512m"
( unset GCN51_DB_PASSWORD   # JMeter never needs the database password; the JWT secret stays in this subshell's environment
  jmeter -n -t "$JMX" -l "$R/results.jtl" -j "$R/jmeter.log" -JfixturesFile="$FIX" -JevidenceDir="$GCN51_DIR/evidence" \
    -Jhttpclient4.retrycount=0 -Jjmeterengine.nongui.port=4551 -Jjmeterengine.nongui.maxport=4551 -Jgcn51.host=localhost -Jgcn51.port=5251 \
    -Jjmeter.save.saveservice.output_format=csv -Jjmeter.save.saveservice.assertion_results_failure_message=true -Jjmeter.save.saveservice.timestamp_format=ms -Jjmeter.save.saveservice.print_field_names=true \
    > "$R/console.txt" 2>&1 ) ; grep -E "summary =|Err:|end of run" "$R/console.txt" | tail -3
echo "--- read-only database-unchanged verification ---"; bash "$GCN51_DIR/gcn51-verify.sh" post | tee "$R/verify-post.txt" | tail -14
echo "--- server-side request count ---";            bash "$GCN51_DIR/gcn51-verify.sh" requests | tee "$R/verify-requests.txt" | tail -6
echo "--- results ---"; python3 "$GCN51_DIR/summarize.py" | tee "$R/summary.txt"
