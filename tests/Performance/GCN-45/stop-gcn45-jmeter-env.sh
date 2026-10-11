#!/usr/bin/env bash
# Stops ONLY the processes this suite started (pid files in the run folder), after checking that each pid's command line is
# really our doctor stub or our published backend. No pkill, no killing by port, no signal other than SIGTERM.
set -u
. "$(dirname "$0")/gcn45-common.sh"
stop_one() {  # $1 pid file  $2 required text in the command line
  [ -f "$1" ] || { echo "no pid file $(basename "$1")"; return; }
  local pid; pid="$(cat "$1")"
  case "$pid" in ''|*[!0-9]*) echo "bad pid in $1"; return;; esac
  local cmd; cmd="$(ps -p "$pid" -o command= 2>/dev/null)"
  [ -n "$cmd" ] || { echo "pid $pid is not running"; rm -f "$1"; return; }
  case "$cmd" in *"$2"*) kill "$pid" && echo "stopped pid $pid ($(basename "$1"))"; rm -f "$1";; *) echo "SKIPPED pid $pid: its command line is not ours";; esac
}
stop_one "$GCN45_RUN_DIR/stub.pid" "gcn45-doctor-stub.py"
for n in A B; do
  pid_file="$GCN45_RUN_DIR/backend-$n.pid"
  # the pid file holds the pid of the subshell child `dotnet AppointmentIntegration.Api.dll` started in the run folder
  stop_one "$pid_file" "AppointmentIntegration.Api.dll"
done
