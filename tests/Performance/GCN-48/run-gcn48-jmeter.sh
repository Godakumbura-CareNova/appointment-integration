#!/usr/bin/env bash
# Runs the GCN-48 plan ONCE: exactly 5 HTTP requests (JM-01..JM-05, one each, one thread, one iteration), then the read-only verification.
#   bash run-gcn48-jmeter.sh           plan only: sends and changes nothing
#   bash run-gcn48-jmeter.sh --yes     runs  (pre-flight -> JMeter -> database/refund-record check -> server request count -> summary)
# The run CHANGES ONE DATABASE ROW (JM-05: appointment 48005 Booked -> Cancelled, one cancellation row, one manual-refund row), so a second run needs a NEW empty database: the pre-flight refuses otherwise.
# No setup, authentication, health-check or teardown request exists anywhere: tokens are minted inside JMeter from GCN48_JWT_SECRET, which reaches ONLY the JMeter process.
# No retries (httpclient4.retrycount=0) and no redirects (the samplers do not follow them). This is NOT a load or concurrency test.
set -u -o pipefail
. "$(dirname "$0")/gcn48-common.sh"
JMX="$GCN48_DIR/GCN48AppointmentCancellationTest.jmx"; FIX="$GCN48_DIR/fixtures/fixtures.json"; R="$GCN48_DIR/results/run"; TS="$(date +%Y%m%d-%H%M%S)"
if [ "${1:-}" != "--yes" ]; then
  echo "PLAN (nothing sent, nothing changed): pre-flight (no HTTP), then JMeter sends 5 requests to localhost:$GCN48_PORT:"
  echo "  JM-01 GET  /api/patient/appointments/48001/cancellation  Patient 1  -> 200 allowed:true (unpaid), 64-hex version"
  echo "  JM-02 GET  /api/patient/appointments/48002/cancellation  Patient 1  -> 200 allowed:false CashAlreadyPaid"
  echo "  JM-03 GET  /api/patient/appointments/48101/cancellation  Patient 1  -> 404 (appointment of patient 2), nothing disclosed"
  echo "  JM-04 GET  /api/patient/appointments/48001/cancellation  Doctor     -> 403"
  echo "  JM-05 POST /api/patient/appointments/48005/cancellation  Patient 1  -> 200 Cancelled, refund Eligible, PendingManualProcessing; read-only SQL then checks the cancellation and refund rows"
  echo "Add --yes to run. Needs a freshly seeded database (see README)."; exit 0
fi
[ -f "$JMX" ] && [ -f "$FIX" ] || gcn48_die "plan or fixtures missing (generate and seed first)"
command -v jmeter >/dev/null || gcn48_die "jmeter not found"
gcn48_load_secrets
bash "$GCN48_DIR/gcn48-preflight.sh" > /dev/null || { cat "$GCN48_DIR/evidence/preflight.txt"; gcn48_die "pre-flight failed: nothing was sent"; }
[ -e "$R" ] && { mv "$R" "$GCN48_DIR/results/run-previous-$TS"; echo "previous results kept in results/run-previous-$TS"; }
mkdir -p "$R"; rm -f "$GCN48_DIR/evidence/jm05-response.json"
export JVM_ARGS="-Xms128m -Xmx512m"
( unset GCN48_DB_PASSWORD   # JMeter never needs the database password; the JWT secret stays in this subshell's environment
  jmeter -n -t "$JMX" -l "$R/results.jtl" -j "$R/jmeter.log" -JfixturesFile="$FIX" -JevidenceDir="$GCN48_DIR/evidence" \
    -Jhttpclient4.retrycount=0 -Jjmeterengine.nongui.port=4548 -Jjmeterengine.nongui.maxport=4548 \
    -Jjmeter.save.saveservice.output_format=csv -Jjmeter.save.saveservice.assertion_results_failure_message=true -Jjmeter.save.saveservice.timestamp_format=ms -Jjmeter.save.saveservice.print_field_names=true \
    > "$R/console.txt" 2>&1 ) ; grep -E "summary =|Err:|end of run" "$R/console.txt" | tail -3
echo "--- read-only database and refund-record verification ---"; bash "$GCN48_DIR/gcn48-verify.sh" post | tee "$R/verify-post.txt" | tail -14
echo "--- server-side request count ---";            bash "$GCN48_DIR/gcn48-verify.sh" requests | tee "$R/verify-requests.txt" | tail -6
echo "--- results ---"; python3 "$GCN48_DIR/summarize.py" | tee "$R/summary.txt"
