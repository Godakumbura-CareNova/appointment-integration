#!/usr/bin/env bash
# Runs the GCN-53 plan ONCE: 6 logical scenarios J01..J06 (24 HTTP samplers, 66 read-only GET requests: J06 loops three samplers 15 times), then the read-only verification.
#   bash run-gcn53-jmeter.sh           plan only: sends and changes nothing
#   bash run-gcn53-jmeter.sh --yes     runs  (pre-flight -> JMeter CLI -> database-unchanged check -> server request count -> summary)
# Results, logs and evidence are written OUTSIDE the repository (default ~/carenova/qa-reports/GCN-53/jmeter). The requests are read-only and safe to repeat; the database must be IDENTICAL after the run.
# Tokens are minted inside JMeter from GCN53_JWT_SECRET, which reaches ONLY the JMeter process. No retries (httpclient4.retrycount=0), no redirects. Functional / response-time smoke test: NOT a load or concurrency test.
set -u -o pipefail
. "$(dirname "$0")/gcn53-common.sh"
JMX="$GCN53_DIR/GCN53AdminDashboardTest.jmx"; FIX="$GCN53_OUT/fixtures/fixtures.json"; R="$GCN53_OUT/results/run"; TS="$(date +%Y%m%d-%H%M%S)"
if [ "${1:-}" != "--yes" ]; then
  echo "PLAN (nothing sent, nothing changed): pre-flight (no HTTP), then JMeter sends 66 read-only GET requests (6 scenarios, 24 samplers) to localhost:$GCN53_PORT:"
  echo "  J01 GET admin appointment summary + appointment-payment summary           Admin        -> 200, 200"
  echo "  J02 GET admin appointment list: default, page 2, search, search page 2, pageSize=101   Admin -> 200 x4, 400"
  echo "  J03 GET admin appointment-income report: 21-day window, 40-day window       Admin        -> 200, 400"
  echo "  J04 GET the four admin endpoints                                            no token     -> 401 x4"
  echo "  J05 GET admin endpoints                          Patient x4, PharmacyStaff x2, Doctor x2 -> 403 x8"
  echo "  J06 15 x (summary + payment summary + list page 1 size 5)                   Admin        -> 200 x45, values consistent, response times within the documented thresholds"
  echo "Add --yes to run. Needs a freshly seeded database (see README)."; exit 0
fi
[ -f "$JMX" ] && [ -f "$FIX" ] || gcn53_die "plan or fixtures missing (generate and seed first)"
command -v jmeter >/dev/null || gcn53_die "jmeter not found"
gcn53_load_secrets
bash "$GCN53_DIR/gcn53-preflight.sh" > /dev/null || { cat "$GCN53_OUT/evidence/preflight.txt"; gcn53_die "pre-flight failed: nothing was sent"; }
[ -e "$R" ] && { mv "$R" "$GCN53_OUT/results/run-previous-$TS"; echo "previous results kept in results/run-previous-$TS"; }
mkdir -p "$R"; rm -f "$GCN53_OUT/evidence/jm05-response.json"
export JVM_ARGS="-Xms128m -Xmx512m"
( unset GCN53_DB_PASSWORD   # JMeter never needs the database password; the JWT secret stays in this subshell's environment
  jmeter -n -t "$JMX" -l "$R/results.jtl" -j "$R/jmeter.log" -JfixturesFile="$FIX" -JevidenceDir="$GCN53_OUT/evidence" \
    -Jhttpclient4.retrycount=0 -Jjmeterengine.nongui.port=4553 -Jjmeterengine.nongui.maxport=4553 -Jgcn53.host=localhost -Jgcn53.port=5253 \
    -Jjmeter.save.saveservice.output_format=csv -Jjmeter.save.saveservice.assertion_results_failure_message=true -Jjmeter.save.saveservice.timestamp_format=ms -Jjmeter.save.saveservice.print_field_names=true \
    > "$R/console.txt" 2>&1 ) ; grep -E "summary =|Err:|end of run" "$R/console.txt" | tail -3
echo "--- read-only database-unchanged verification ---"; bash "$GCN53_DIR/gcn53-verify.sh" post | tee "$R/verify-post.txt" | tail -14
echo "--- server-side request count ---";            bash "$GCN53_DIR/gcn53-verify.sh" requests | tee "$R/verify-requests.txt" | tail -6
echo "--- results ---"; python3 "$GCN53_DIR/summarize.py" | tee "$R/summary.txt"
