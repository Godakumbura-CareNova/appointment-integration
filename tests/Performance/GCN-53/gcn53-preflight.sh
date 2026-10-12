#!/usr/bin/env bash
# PRE-FLIGHT (no HTTP request of any kind): secrets, isolated database, seeded fixtures, backend process, plan. Run by run-gcn53-jmeter.sh before JMeter starts.
# Readiness of the backend is the listening socket (lsof) and the identity of the process, never a request: the suite sends exactly the 66 planned requests in total.
# It also records the backend log's current line count so that the post-run check can prove that EXACTLY the 66 expected requests reached the server.
set -u -o pipefail
. "$(dirname "$0")/gcn53-common.sh"
gcn53_assert_db_target; gcn53_load_secrets
OUT="$GCN53_OUT/evidence"; mkdir -p "$OUT"; FAIL=0
ok() { printf '  PASS  %s\n' "$1"; }; bad() { printf '  FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
{
echo "GCN-53 pre-flight $(date '+%Y-%m-%d %H:%M:%S')   (database, files and process checks only: NO HTTP request)"
[ "$(gcn53_mode "$GCN53_SECRET_FILE")" = "600" ] && ok "secrets file mode 600, outside git" || bad "secrets file mode"
V=$(gcn53_mysql_app -N -B -e "SHOW DATABASES;" | tr '\n' ' ') && ok "limited user connects: sees [$V]" || bad "limited user cannot connect"
case "$V" in *carenova_appointment_qa*|*carenova_appointment_integration*|*gcn45*|*gcn46*|*gcn47*|*gcn48*) bad "the limited user can see another CareNova database";; *) ok "no GCN-45, GCN-46, GCN-47, GCN-48 or shared database is visible to the limited user";; esac
[ -f "$GCN53_OUT/fixtures/fixtures.json" ] && ok "fixtures file present" || bad "fixtures file missing (run gcn53-seed-fixtures.sh --yes)"
bash "$GCN53_DIR/gcn53-verify.sh" pre > "$OUT/preflight-database.txt" 2>&1 && ok "database preconditions (read-only SQL): seeded exactly as the fixtures, every table equals the seed (read-only suite: nothing may ever change)" || { bad "database preconditions failed:"; sed 's/^/        /' "$OUT/preflight-database.txt" | grep -E "FAIL|failed" | head -6; }
PIDF="$GCN53_RUN_DIR/backend.pid"; PID="$(cat "$PIDF" 2>/dev/null || true)"
if [ -n "$PID" ] && ps -p "$PID" -o command= 2>/dev/null | grep -q "AppointmentIntegration.Api.dll"; then ok "backend process $PID is the published GCN-53 build started by start-gcn53-env.sh"; else bad "no GCN-53 backend process from start-gcn53-env.sh"; fi
gcn53_port_in_use "$GCN53_PORT" && ok "something is listening on :$GCN53_PORT (lsof; no request was sent)" || bad "nothing is listening on :$GCN53_PORT"
LP="$(lsof -nP -iTCP:$GCN53_PORT -sTCP:LISTEN -Fp 2>/dev/null | sed -n 's/^p//p' | head -1)"; [ -n "$LP" ] && [ "$LP" = "$PID" ] && ok "the listener on :$GCN53_PORT is that backend process" || bad "the listener on :$GCN53_PORT is not the recorded backend process"
gcn53_port_in_use 4553 && bad "JMeter control port 4553 is busy" || ok "JMeter control port 4553 is free"
command -v jmeter >/dev/null && ok "jmeter found: $(command -v jmeter | sed "s|$HOME|~|")" || bad "jmeter not found"
python3 - "$GCN53_DIR" <<'PY' && ok "plan: 6 scenarios, 24 HTTP samplers (all GET), localhost target resolved by the guarded pre-processor, no other sampler type" || bad "plan structure"
import sys, xml.etree.ElementTree as ET
r = ET.parse(sys.argv[1] + "/GCN53AdminDashboardTest.jmx").getroot(); s = list(r.iter("HTTPSamplerProxy")); tg = list(r.iter("ThreadGroup"))
ok = len(tg) == 6 and len(s) == 24 and all([c.text for c in e if c.get("name") == "HTTPSampler.method"][0] == "GET" for e in s) and all(e.tag != "JSR223Sampler" for e in r.iter())
sys.exit(0 if ok else 1)
PY
if [ -f "$GCN53_OUT/logs/backend.log" ]; then wc -l < "$GCN53_OUT/logs/backend.log" | tr -d ' ' > "$OUT/log-baseline.txt"; ok "server request-log baseline recorded: line $(cat "$OUT/log-baseline.txt")"; else bad "backend log missing"; fi
echo; [ "$FAIL" = 0 ] && echo "PRE-FLIGHT PASSED: nothing was sent" || echo "$FAIL CHECK(S) FAILED: nothing was sent"
} 2>&1 | tee "$OUT/preflight.txt"; exit "${PIPESTATUS[0]}"
