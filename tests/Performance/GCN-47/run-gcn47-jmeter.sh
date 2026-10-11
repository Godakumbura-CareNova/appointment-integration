#!/usr/bin/env bash
# Runs the GCN-47 plan ONCE: exactly 5 HTTP requests (JM-01..JM-05, one each, one thread, one iteration), then the read-only verification.
#   bash run-gcn47-jmeter.sh           plan only: sends and changes nothing
#   bash run-gcn47-jmeter.sh --yes     runs  (pre-flight -> JMeter -> database/audit check -> server request count -> summary)
# The run CHANGES ONE DATABASE ROW (JM-05: appointment 47002 Booked -> Confirmed, one audit row), so a second run needs a NEW empty database: the pre-flight refuses otherwise.
# No setup, authentication, health-check or teardown request exists anywhere: tokens are minted inside JMeter from GCN47_JWT_SECRET, which reaches ONLY the JMeter process.
# No retries (httpclient4.retrycount=0) and no redirects (the samplers do not follow them). This is NOT a load or concurrency test.
set -u -o pipefail
. "$(dirname "$0")/gcn47-common.sh"
JMX="$GCN47_DIR/GCN47DoctorAppointmentsTest.jmx"; FIX="$GCN47_DIR/fixtures/fixtures.json"; R="$GCN47_DIR/results/run"; TS="$(date +%Y%m%d-%H%M%S)"
if [ "${1:-}" != "--yes" ]; then
  echo "PLAN (nothing sent, nothing changed): pre-flight (no HTTP), then JMeter sends 5 requests to localhost:$GCN47_PORT:"
  echo "  JM-01 GET   /api/doctor/appointments                      Doctor 1  -> 200"
  echo "  JM-02 GET   /api/doctor/appointments/47001                Doctor 1  -> 200"
  echo "  JM-03 GET   /api/doctor/appointments/47101 (doctor 2's)   Doctor 1  -> 404"
  echo "  JM-04 GET   /api/doctor/appointments                      Patient   -> 403"
  echo "  JM-05 PATCH /api/doctor/appointments/47002/status         Doctor 1  -> 200 (Booked -> Confirmed), then read-only SQL checks the audit row"
  echo "Add --yes to run. Needs a freshly seeded database (see README)."; exit 0
fi
[ -f "$JMX" ] && [ -f "$FIX" ] || gcn47_die "plan or fixtures missing (generate and seed first)"
command -v jmeter >/dev/null || gcn47_die "jmeter not found"
gcn47_load_secrets
bash "$GCN47_DIR/gcn47-preflight.sh" > /dev/null || { cat "$GCN47_DIR/evidence/preflight.txt"; gcn47_die "pre-flight failed: nothing was sent"; }
[ -e "$R" ] && { mv "$R" "$GCN47_DIR/results/run-previous-$TS"; echo "previous results kept in results/run-previous-$TS"; }
mkdir -p "$R"; rm -f "$GCN47_DIR/evidence/jm05-response.json"
export JVM_ARGS="-Xms128m -Xmx512m"
( unset GCN47_DB_PASSWORD   # JMeter never needs the database password; the JWT secret stays in this subshell's environment
  jmeter -n -t "$JMX" -l "$R/results.jtl" -j "$R/jmeter.log" -JfixturesFile="$FIX" -JevidenceDir="$GCN47_DIR/evidence" \
    -Jhttpclient4.retrycount=0 -Jjmeterengine.nongui.port=4547 -Jjmeterengine.nongui.maxport=4547 \
    -Jjmeter.save.saveservice.output_format=csv -Jjmeter.save.saveservice.assertion_results_failure_message=true -Jjmeter.save.saveservice.timestamp_format=ms -Jjmeter.save.saveservice.print_field_names=true \
    > "$R/console.txt" 2>&1 ) ; grep -E "summary =|Err:|end of run" "$R/console.txt" | tail -3
echo "--- read-only database and audit verification ---"; bash "$GCN47_DIR/gcn47-verify.sh" post | tee "$R/verify-post.txt" | tail -14
echo "--- server-side request count ---";            bash "$GCN47_DIR/gcn47-verify.sh" requests | tee "$R/verify-requests.txt" | tail -6
echo "--- results ---"; python3 "$GCN47_DIR/summarize.py" | tee "$R/summary.txt"
