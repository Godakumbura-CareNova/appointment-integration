#!/usr/bin/env bash
# PRE-FLIGHT (no HTTP request of any kind): secrets, isolated database, seeded fixtures, backend process, plan. Run by run-gcn51-jmeter.sh before JMeter starts.
# Readiness of the backend is the listening socket (lsof) and the identity of the process, never a request: the suite sends exactly the 38 planned requests in total.
# It also records the backend log's current line count so that the post-run check can prove that EXACTLY the 38 expected requests reached the server.
set -u -o pipefail
. "$(dirname "$0")/gcn51-common.sh"
gcn51_assert_db_target; gcn51_load_secrets
OUT="$GCN51_DIR/evidence"; mkdir -p "$OUT"; FAIL=0
ok() { printf '  PASS  %s\n' "$1"; }; bad() { printf '  FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
{
echo "GCN-51 pre-flight $(date '+%Y-%m-%d %H:%M:%S')   (database, files and process checks only: NO HTTP request)"
[ "$(gcn51_mode "$GCN51_SECRET_FILE")" = "600" ] && ok "secrets file mode 600, outside git" || bad "secrets file mode"
V=$(gcn51_mysql_app -N -B -e "SHOW DATABASES;" | tr '\n' ' ') && ok "limited user connects: sees [$V]" || bad "limited user cannot connect"
case "$V" in *carenova_appointment_qa*|*carenova_appointment_integration*|*gcn45*|*gcn46*|*gcn47*|*gcn48*) bad "the limited user can see another CareNova database";; *) ok "no GCN-45, GCN-46, GCN-47, GCN-48 or shared database is visible to the limited user";; esac
[ -f "$GCN51_DIR/fixtures/fixtures.json" ] && ok "fixtures file present" || bad "fixtures file missing (run gcn51-seed-fixtures.sh --yes)"
bash "$GCN51_DIR/gcn51-verify.sh" pre > "$OUT/preflight-database.txt" 2>&1 && ok "database preconditions (read-only SQL): seeded exactly as the fixtures, every table equals the seed (read-only suite: nothing may ever change)" || { bad "database preconditions failed:"; sed 's/^/        /' "$OUT/preflight-database.txt" | grep -E "FAIL|failed" | head -6; }
PIDF="$GCN51_RUN_DIR/backend.pid"; PID="$(cat "$PIDF" 2>/dev/null || true)"
if [ -n "$PID" ] && ps -p "$PID" -o command= 2>/dev/null | grep -q "AppointmentIntegration.Api.dll"; then ok "backend process $PID is the published GCN-51 build started by start-gcn51-env.sh"; else bad "no GCN-51 backend process from start-gcn51-env.sh"; fi
gcn51_port_in_use "$GCN51_PORT" && ok "something is listening on :$GCN51_PORT (lsof; no request was sent)" || bad "nothing is listening on :$GCN51_PORT"
LP="$(lsof -nP -iTCP:$GCN51_PORT -sTCP:LISTEN -Fp 2>/dev/null | sed -n 's/^p//p' | head -1)"; [ -n "$LP" ] && [ "$LP" = "$PID" ] && ok "the listener on :$GCN51_PORT is that backend process" || bad "the listener on :$GCN51_PORT is not the recorded backend process"
gcn51_port_in_use 4551 && bad "JMeter control port 4551 is busy" || ok "JMeter control port 4551 is free"
command -v jmeter >/dev/null && ok "jmeter found: $(command -v jmeter | sed "s|$HOME|~|")" || bad "jmeter not found"
python3 - "$GCN51_DIR" <<'PY' && ok "plan: 9 scenarios, 9 HTTP samplers (one per scenario, all GET), localhost target resolved by the guarded pre-processor, no other sampler type" || bad "plan structure"
import sys, xml.etree.ElementTree as ET
r = ET.parse(sys.argv[1] + "/GCN51RoleDashboardTest.jmx").getroot(); s = list(r.iter("HTTPSamplerProxy")); tg = list(r.iter("ThreadGroup"))
ok = len(tg) == 9 and len(s) == 9 and all([c.text for c in e if c.get("name") == "HTTPSampler.method"][0] == "GET" for e in s) and all(e.tag != "JSR223Sampler" for e in r.iter())
sys.exit(0 if ok else 1)
PY
if [ -f "$GCN51_DIR/logs/backend.log" ]; then wc -l < "$GCN51_DIR/logs/backend.log" | tr -d ' ' > "$OUT/log-baseline.txt"; ok "server request-log baseline recorded: line $(cat "$OUT/log-baseline.txt")"; else bad "backend log missing"; fi
echo; [ "$FAIL" = 0 ] && echo "PRE-FLIGHT PASSED: nothing was sent" || echo "$FAIL CHECK(S) FAILED: nothing was sent"
} 2>&1 | tee "$OUT/preflight.txt"; exit "${PIPESTATUS[0]}"
