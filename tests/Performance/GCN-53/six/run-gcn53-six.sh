#!/usr/bin/env bash
# Runs the GCN-53 SIX-REQUEST plan ONCE: 6 test cases T01..T06, 6 HTTP GET samplers (one per test case), one thread, one iteration, 6 requests in total, then the read-only verification.
#   bash run-gcn53-six.sh           plan only: sends and changes nothing
#   bash run-gcn53-six.sh --yes     runs  (pre-flight -> JMeter CLI -> database-unchanged check -> server request check -> report)
# Results and evidence go to ~/carenova/qa-reports/GCN-53/jmeter-six (outside the repository); the 66-request suite's results in ../jmeter are never touched.
# Tokens are minted inside JMeter from GCN53_JWT_SECRET, which reaches ONLY the JMeter process. No retries (httpclient4.retrycount=0), no redirects, no loops.
set -u -o pipefail
SIX_DIR="$(cd "$(dirname "$0")" && pwd)"
export GCN53_OUT_DIR="${GCN53_OUT_DIR:-$HOME/carenova/qa-reports/GCN-53/jmeter-six}"
. "$SIX_DIR/../gcn53-common.sh"
JMX="$SIX_DIR/GCN53AdminDashboardSixTest.jmx"; FIX="$GCN53_OUT/fixtures/fixtures.json"; R="$GCN53_OUT/results/run"; TS="$(date +%Y%m%d-%H%M%S)"
if [ "${1:-}" != "--yes" ]; then
  echo "PLAN (nothing sent, nothing changed): pre-flight (no HTTP), then JMeter sends 6 read-only GET requests (6 test cases, one request each) to localhost:$GCN53_PORT:"
  echo "  T01 GET /api/admin/dashboard/appointments               Admin    -> 200"
  echo "  T02 GET /api/admin/dashboard/appointment-payments       Admin    -> 200"
  echo "  T03 GET /api/admin/appointments?page=2&pageSize=5       Admin    -> 200"
  echo "  T04 GET /api/admin/reports/appointment-income (21 days) Admin    -> 200"
  echo "  T05 GET /api/admin/dashboard/appointment-payments       no token -> 401"
  echo "  T06 GET /api/admin/appointments                         Patient  -> 403"
  echo "Add --yes to run. Needs a freshly seeded database (see README)."; exit 0
fi
[ -f "$JMX" ] && [ -f "$FIX" ] || gcn53_die "plan or fixtures missing (generate and seed first)"
command -v jmeter >/dev/null || gcn53_die "jmeter not found"
gcn53_load_secrets
bash "$SIX_DIR/gcn53-six-preflight.sh" > /dev/null || { cat "$GCN53_OUT/evidence/preflight.txt"; gcn53_die "pre-flight failed: nothing was sent"; }
[ -e "$R" ] && { mv "$R" "$GCN53_OUT/results/run-previous-$TS"; echo "previous results kept in results/run-previous-$TS"; }
mkdir -p "$R"; true
export JVM_ARGS="-Xms128m -Xmx512m"
( unset GCN53_DB_PASSWORD   # JMeter never needs the database password; the JWT secret stays in this subshell's environment
  jmeter -n -t "$JMX" -l "$R/results.jtl" -j "$R/jmeter.log" -JfixturesFile="$FIX" -JevidenceDir="$GCN53_OUT/evidence" \
    -Jhttpclient4.retrycount=0 -Jjmeterengine.nongui.port=4553 -Jjmeterengine.nongui.maxport=4553 -Jgcn53.host=localhost -Jgcn53.port=5253 \
    -Jjmeter.save.saveservice.output_format=csv -Jjmeter.save.saveservice.assertion_results_failure_message=true -Jjmeter.save.saveservice.timestamp_format=ms -Jjmeter.save.saveservice.print_field_names=true \
    > "$R/console.txt" 2>&1 ) ; grep -E "summary =|Err:|end of run" "$R/console.txt" | tail -3
echo "--- read-only database-unchanged verification ---"; bash "$GCN53_DIR/gcn53-verify.sh" post | tee "$R/verify-post.txt" | tail -14
echo "--- server-side request count ---";            python3 "$SIX_DIR/gcn53_six_requests.py" | tee "$R/verify-requests.txt" | tail -6
echo "--- results ---"; python3 "$SIX_DIR/summarize_six.py" | tee "$R/summary.txt"
