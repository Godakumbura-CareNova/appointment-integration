#!/usr/bin/env bash
# PRE-FLIGHT (no HTTP request of any kind): secrets, isolated database, seeded fixtures, backend process, plan. Run by run-gcn48-jmeter.sh before JMeter starts.
# Readiness of the backend is the listening socket (lsof) and the identity of the process, never a request: the suite sends exactly five requests in total.
# It also records the backend log's current line count so that the post-run check can prove that EXACTLY five requests reached the server.
set -u -o pipefail
. "$(dirname "$0")/gcn48-common.sh"
gcn48_assert_db_target; gcn48_load_secrets
OUT="$GCN48_DIR/evidence"; mkdir -p "$OUT"; FAIL=0
ok() { printf '  PASS  %s\n' "$1"; }; bad() { printf '  FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
{
echo "GCN-48 pre-flight $(date '+%Y-%m-%d %H:%M:%S')   (database, files and process checks only: NO HTTP request)"
[ "$(gcn48_mode "$GCN48_SECRET_FILE")" = "600" ] && ok "secrets file mode 600, outside git" || bad "secrets file mode"
V=$(gcn48_mysql_app -N -B -e "SHOW DATABASES;" | tr '\n' ' ') && ok "limited user connects: sees [$V]" || bad "limited user cannot connect"
case "$V" in *carenova_appointment_qa*|*carenova_appointment_integration*|*gcn45*|*gcn46*|*gcn47*) bad "the limited user can see another CareNova database";; *) ok "no GCN-45, GCN-46, GCN-47 or shared database is visible to the limited user";; esac
[ -f "$GCN48_DIR/fixtures/fixtures.json" ] && ok "fixtures file present" || bad "fixtures file missing (run gcn48-seed-fixtures.sh --yes)"
bash "$GCN48_DIR/gcn48-verify.sh" pre > "$OUT/preflight-database.txt" 2>&1 && ok "database preconditions (read-only SQL): seeded exactly as the fixtures, nothing cancelled yet, no cancellation or refund row" || { bad "database preconditions failed:"; sed 's/^/        /' "$OUT/preflight-database.txt" | grep -E "FAIL|failed" | head -6; }
PIDF="$GCN48_RUN_DIR/backend.pid"; PID="$(cat "$PIDF" 2>/dev/null || true)"
if [ -n "$PID" ] && ps -p "$PID" -o command= 2>/dev/null | grep -q "AppointmentIntegration.Api.dll"; then ok "backend process $PID is the published GCN-48 build started by start-gcn48-env.sh"; else bad "no GCN-48 backend process from start-gcn48-env.sh"; fi
gcn48_port_in_use "$GCN48_PORT" && ok "something is listening on :$GCN48_PORT (lsof; no request was sent)" || bad "nothing is listening on :$GCN48_PORT"
LP="$(lsof -nP -iTCP:$GCN48_PORT -sTCP:LISTEN -Fp 2>/dev/null | sed -n 's/^p//p' | head -1)"; [ -n "$LP" ] && [ "$LP" = "$PID" ] && ok "the listener on :$GCN48_PORT is that backend process" || bad "the listener on :$GCN48_PORT is not the recorded backend process"
bash "$GCN48_DIR/gcn48-check-version.sh" --db > "$OUT/preflight-version.txt" 2>&1 && ok "confirmation versions: the offline port equals the real backend code, and the real service reading the seeded rows gives the stored versions (no HTTP, SELECT only)" || { bad "version check failed:"; grep -E "FAIL|failed" "$OUT/preflight-version.txt" | head -4 | sed 's/^/        /'; }
gcn48_port_in_use 4548 && bad "JMeter control port 4548 is busy" || ok "JMeter control port 4548 is free"
command -v jmeter >/dev/null && ok "jmeter found: $(command -v jmeter | sed "s|$HOME|~|")" || bad "jmeter not found"
python3 - "$GCN48_DIR" <<'PY' && ok "plan: exactly 5 HTTP samplers (4 GET + 1 POST), one thread and one loop each, no other sampler type" || bad "plan structure"
import sys, xml.etree.ElementTree as ET
r = ET.parse(sys.argv[1] + "/GCN48AppointmentCancellationTest.jmx").getroot(); s = list(r.iter("HTTPSamplerProxy"))
m = sorted({[c.text for c in e if c.get("name") == "HTTPSampler.method"][0] for e in s}); ok = len(s) == 5 and m == ["GET", "POST"]
ok = ok and all(e.tag != "JSR223Sampler" for e in r.iter()) and all([c.text for c in e if c.get("name") == "ThreadGroup.num_threads"][0] == "1" for e in r.iter("ThreadGroup"))
sys.exit(0 if ok else 1)
PY
if [ -f "$GCN48_DIR/logs/backend.log" ]; then wc -l < "$GCN48_DIR/logs/backend.log" | tr -d ' ' > "$OUT/log-baseline.txt"; ok "server request-log baseline recorded: line $(cat "$OUT/log-baseline.txt")"; else bad "backend log missing"; fi
echo; [ "$FAIL" = 0 ] && echo "PRE-FLIGHT PASSED: nothing was sent" || echo "$FAIL CHECK(S) FAILED: nothing was sent"
} 2>&1 | tee "$OUT/preflight.txt"; exit "${PIPESTATUS[0]}"
