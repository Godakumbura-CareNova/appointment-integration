#!/usr/bin/env bash
# Runs ONE phase of the GCN-46 plan with the JMeter CLI against the local isolated backend (:5246). All requests are GET (read-only).
#   --phase functional   JM-01..JM-06 (about 1,930 requests)       --phase load   JM-07 increased load and recovery (about 8,000 requests, ~4 minutes, monitored)
#   bash run-gcn46-jmeter.sh --phase functional           plan only         bash run-gcn46-jmeter.sh --phase functional --yes    runs
# Secrets reach ONLY the JMeter process environment. Earlier results of the same phase are MOVED aside, never overwritten. The load phase refuses to start when the
# machine is already busy and is watched by gcn46_monitor.py (stops JMeter on unsafe load; the scenario is then reported STOPPED, not passed).
set -u -o pipefail
. "$(dirname "$0")/gcn46-common.sh"
PHASE=""; YES=0
while [ $# -gt 0 ]; do case "$1" in --phase) PHASE="${2:-}"; shift 2;; --yes) YES=1; shift;; *) gcn46_die "unknown argument: $1";; esac; done
case "$PHASE" in functional|load) ;; *) gcn46_die "usage: --phase functional|load [--yes]";; esac
JMX="$GCN46_DIR/GCN46PatientAppointmentsTest.jmx"; FIX="$GCN46_DIR/fixtures/fixtures.json"; R="$GCN46_DIR/results/$PHASE"; TS="$(date +%Y%m%d-%H%M%S)"; STOPPORT=4546
if [ "$YES" != "1" ]; then echo "PLAN (nothing sent): phase $PHASE against localhost:$GCN46_PORT with synthetic tokens. All requests are GET. Add --yes to run."; exit 0; fi
[ -f "$JMX" ] && [ -f "$FIX" ] || gcn46_die "plan or fixtures missing (generate and seed first)"
command -v jmeter >/dev/null || gcn46_die "jmeter not found"
gcn46_load_secrets
bash "$GCN46_DIR/gcn46-validate-env.sh" >/dev/null || gcn46_die "validation gate failed (see $GCN46_DIR/evidence/validate-env.txt); nothing was run"
if [ "$PHASE" = "load" ]; then
  read -r LOAD1 FREE < <(python3 "$GCN46_DIR/gcn46_monitor.py" --probe)       # "load1 free_memory_percent" (-1 = this OS does not report it: that check is skipped)
  python3 -c "import sys; l=float('$LOAD1'); f=float('$FREE'); sys.exit(0 if l<6 and (f<0 or f>=30) else 1)" || gcn46_die "machine is busy (load $LOAD1, free memory $FREE%): close other heavy apps (e.g. open JMeter windows) and retry"
  [ "${FREE%.*}" = "-1" ] && echo "note: free memory is not reported on this OS; only the load average is checked"
fi
[ -e "$R" ] && { mv "$R" "$GCN46_DIR/results/$PHASE-previous-$TS"; echo "previous results kept in results/$PHASE-previous-$TS"; }
mkdir -p "$R"; unset GCN46_DB_PASSWORD   # JMeter never needs the database password
export JVM_ARGS="-Xms256m -Xmx1g"; DONE="$R/run.done"; rm -f "$DONE"
echo "Running phase $PHASE ..."
jmeter -n -t "$JMX" -l "$R/results.jtl" -j "$R/jmeter.log" -e -o "$R/dashboard" -Jphase="$PHASE" -JfixturesFile="$FIX" -JevidenceDir="$GCN46_DIR/evidence" \
  -Jjmeterengine.nongui.port=$STOPPORT -Jjmeterengine.nongui.maxport=$STOPPORT \
  -Jjmeter.save.saveservice.output_format=csv -Jjmeter.save.saveservice.assertion_results_failure_message=true -Jjmeter.save.saveservice.timestamp_format=ms -Jjmeter.save.saveservice.print_field_names=true \
  > "$R/console.txt" 2>&1 &
JM=$!
if [ "$PHASE" = "load" ]; then
  BPID="$(cat "$GCN46_RUN_DIR/backend.pid" 2>/dev/null || echo 0)"
  python3 "$GCN46_DIR/gcn46_monitor.py" --jtl "$R/results.jtl" --stop-file "$R/monitor-stop.txt" --done-file "$DONE" --log "$R/monitor.csv" --port $STOPPORT --backend-pid "$BPID" &
  MON=$!
fi
wait "$JM"; touch "$DONE"; [ "${MON:-}" ] && wait "$MON"
grep -E "summary =|Err:|end of run" "$R/console.txt" | tail -4
[ -f "$R/monitor-stop.txt" ] && echo "!!! STOPPED BY THE SAFETY MONITOR: $(cat "$R/monitor-stop.txt")"
echo "--- read-only database evidence ---"; bash "$GCN46_DIR/gcn46-db-evidence.sh" "after-$PHASE" | tail -n 22
echo "--- results ---"; python3 "$GCN46_DIR/summarize.py" --phase "$PHASE" | tee "$R/summary.txt"
echo "Results file: $R/results.jtl   Dashboard: $R/dashboard/index.html"
