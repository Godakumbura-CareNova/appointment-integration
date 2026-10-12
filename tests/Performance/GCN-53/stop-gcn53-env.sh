#!/usr/bin/env bash
# Stops ONLY the backend this suite started (pid file in the run folder), after checking the pid's command line is our published backend. No pkill, no kill by port.
set -u
. "$(dirname "$0")/gcn53-common.sh"
f="$GCN53_RUN_DIR/backend.pid"; [ -f "$f" ] || { echo "no pid file: nothing to stop"; exit 0; }
pid="$(cat "$f")"; case "$pid" in ''|*[!0-9]*) echo "bad pid in $f"; exit 1;; esac
cmd="$(ps -p "$pid" -o command= 2>/dev/null)"; [ -n "$cmd" ] || { echo "pid $pid is not running"; rm -f "$f"; exit 0; }
case "$cmd" in *"AppointmentIntegration.Api.dll"*) kill "$pid" && echo "stopped pid $pid" && rm -f "$f";; *) echo "SKIPPED pid $pid: its command line is not ours";; esac
