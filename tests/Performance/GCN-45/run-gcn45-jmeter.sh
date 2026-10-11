#!/usr/bin/env bash
# Runs ONE phase of the GCN-45 JMeter plan (command line) against the local test environment. Each phase is a separate approval.
#   --phase seed        FX fixtures: 3 appointments, 2 payments, 1 online attempt (state-changing)
#   --phase readonly    JM-01..JM-04 (GET requests, and POSTs that must be rejected; no state change)
#   --phase state       JM-05, JM-06, JM-08 (state-changing)
#   --phase concurrent  JM-07 (state-changing, concurrent)
#   bash run-gcn45-jmeter.sh --phase readonly            plan only (checks nothing, sends nothing)
#   bash run-gcn45-jmeter.sh --phase readonly --yes      runs
# Targets are fixed in the plan: localhost 5235 (stub), 5236 (backend A), 5237 (backend B). Secrets reach ONLY the JMeter process environment.
# Results of an earlier run of the same phase are MOVED aside, never overwritten or deleted.
set -u -o pipefail
. "$(dirname "$0")/gcn45-common.sh"
PHASE=""; YES=0
while [ $# -gt 0 ]; do case "$1" in --phase) PHASE="${2:-}"; shift 2;; --yes) YES=1; shift;; *) gcn45_die "unknown argument: $1";; esac; done
case "$PHASE" in seed|readonly|state|concurrent) ;; *) gcn45_die "usage: --phase seed|readonly|state|concurrent [--yes]";; esac
JMX="$GCN45_REPORT_DIR/GCN45AppointmentPaymentTest.jmx"; FIX="$GCN45_REPORT_DIR/fixtures.json"; R="$GCN45_REPORT_DIR/results/$PHASE"; TS="$(date +%Y%m%d-%H%M%S)"
case "$PHASE" in
  seed) DESC="creates 3 appointments, 2 payments and 1 online attempt in $GCN45_DB_NAME";;
  readonly) DESC="JM-01..JM-04: 213 requests, GETs and rejected POSTs only";;
  state) DESC="JM-05, JM-06, JM-08: creates appointments, payments and online attempts in $GCN45_DB_NAME; toggles the local doctor stub";;
  concurrent) DESC="JM-07: concurrent writes to $GCN45_DB_NAME (5 simultaneous users per step)";;
esac
if [ "$YES" != "1" ]; then echo "PLAN (nothing sent): phase $PHASE - $DESC. Targets: localhost:$GCN45_PORT_STUB/$GCN45_PORT_A/$GCN45_PORT_B only. Add --yes to run."; exit 0; fi
[ -f "$JMX" ] || gcn45_die "plan not found: $JMX (run gen_gcn45_jmx.py)"
command -v jmeter >/dev/null || gcn45_die "jmeter not found"
gcn45_load_secrets
code() { curl -s -o /dev/null -m 6 -w '%{http_code}' "$1" 2>/dev/null; }
[ "$(code "http://127.0.0.1:$GCN45_PORT_STUB/__stats")" = "200" ] || gcn45_die "doctor stub on $GCN45_PORT_STUB is not running (start-gcn45-jmeter-env.sh)"
[ "$(code "http://localhost:$GCN45_PORT_A/api/appointments/1/payment")" = "401" ] || gcn45_die "backend A on $GCN45_PORT_A is not running"
[ "$PHASE" != "state" ] || [ "$(code "http://localhost:$GCN45_PORT_B/api/appointments/1/payment")" = "401" ] || gcn45_die "backend B on $GCN45_PORT_B is not running"
[ "$PHASE" != "readonly" ] || [ -f "$FIX" ] || gcn45_die "no fixtures.json: run --phase seed first"
if [ "$PHASE" = "seed" ] && [ -f "$FIX" ]; then mv "$FIX" "$GCN45_REPORT_DIR/fixtures-previous-$TS.json"; echo "previous fixtures kept as fixtures-previous-$TS.json"; fi
[ -e "$R" ] && { mv "$R" "$GCN45_REPORT_DIR/results/$PHASE-previous-$TS"; echo "previous results kept in results/$PHASE-previous-$TS"; }
mkdir -p "$R"
unset GCN45_DB_PASSWORD   # JMeter never needs the database password (the evidence script loads it itself)
echo "Running phase $PHASE ..."
jmeter -n -t "$JMX" -l "$R/results.jtl" -j "$R/jmeter.log" -e -o "$R/dashboard" \
  -Jphase="$PHASE" -JfixturesFile="$FIX" \
  -Jjmeter.save.saveservice.output_format=csv -Jjmeter.save.saveservice.assertion_results_failure_message=true \
  -Jjmeter.save.saveservice.timestamp_format=ms -Jjmeter.save.saveservice.print_field_names=true 2>&1 | grep -E "summary =|Err:|end of run|Exception" | tee "$R/console.txt"
echo "--- read-only database evidence ---"; bash "$GCN45_REPORT_DIR/gcn45-db-evidence.sh" "after-$PHASE" | tail -n 25
echo "--- results ---"; python3 "$GCN45_REPORT_DIR/summarize.py" --phase "$PHASE" | tee "$R/summary.txt"
echo "Results file: $R/results.jtl   Dashboard: $R/dashboard/index.html"
