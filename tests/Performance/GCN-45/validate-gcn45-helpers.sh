#!/usr/bin/env bash
# STATIC validation of the GCN-45 helper scripts and the JMeter plan. It only READS files: it executes none of the helpers, connects to nothing.
# Checks: syntax, destructive commands, protected databases/ports, secret exposure, unsafe process termination, plan targets.
set -u
D="$(cd "$(dirname "$0")" && pwd)"; cd "$D" || exit 1
FILES="gcn45-common.sh gcn45-make-test-secrets.sh gcn45-create-database.sh gcn45-preview-migrations.sh gcn45-apply-migrations.sh start-gcn45-jmeter-env.sh stop-gcn45-jmeter-env.sh gcn45-db-evidence.sh run-gcn45-jmeter.sh"
FAIL=0; ok() { printf '  PASS  %s\n' "$1"; }; bad() { printf '  FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
echo "1. Syntax"; for f in $FILES; do bash -n "$f" 2>/dev/null && ok "bash -n $f" || bad "bash -n $f"; done
for f in gcn45-doctor-stub.py gen_gcn45_jmx.py summarize.py; do python3 -m py_compile "$f" 2>/dev/null && ok "python compile $f" || bad "python compile $f"; done; rm -rf __pycache__
echo "2. Destructive commands (code lines only, comments excluded)"
code() { grep -vE '^[[:space:]]*#' "$@"; }
chk() { local label="$1" pat="$2"; shift 2; if code $FILES | grep -nE "$pat" >/dev/null 2>&1; then bad "$label: $(code $FILES | grep -nE "$pat" | head -3 | tr '\n' ' ')"; else ok "$label"; fi; }
chk "no DROP DATABASE / DROP USER / DROP TABLE" 'DROP[[:space:]]+(DATABASE|USER|TABLE|SCHEMA)'
chk "no DELETE FROM / TRUNCATE / UPDATE statements" '(DELETE[[:space:]]+FROM|TRUNCATE[[:space:]]+TABLE|UPDATE[[:space:]]+[A-Za-z`])'
chk "no rm -rf / rm -r" 'rm[[:space:]]+-[a-zA-Z]*r'
chk "no mysqldump, no git commit/push/add" '(mysqldump|git[[:space:]]+(commit|push|add|reset|checkout|clean))'
chk "no dotnet ef database drop / update against defaults" 'dotnet[[:space:]]+ef[[:space:]]+database'
chk "no IF NOT EXISTS (an existing database or user must stop the run)" 'CREATE[[:space:]]+(DATABASE|USER)[[:space:]]+IF'
echo "3. Database and port targets"
# the one allowed mention: the post-creation isolation check that must FAIL if the limited user can see another CareNova database
if code $FILES | grep -vE 'ISOLATION FAILED' | grep -nE '(carenova_appointment_qa|carenova_appointment_integration|carenova_pharmacy|carenova_user|carenova_doctor)' >/dev/null; then bad "shared QA databases appear in a code line"; else ok "shared QA databases appear in no code line (except the isolation check that fails if they are visible)"; fi
chk "no mysql connection as root with an inline password / --password" '(--password|[[:space:]]-p[A-Za-z0-9]{3,}|Password=[A-Za-z0-9]+;)'
grep -c 'carenova_appointment_gcn45_qa' gcn45-common.sh >/dev/null && ok "database name is a readonly constant in gcn45-common.sh" || bad "database constant missing"
grep -q 'readonly GCN45_DB_NAME="carenova_appointment_gcn45_qa"' gcn45-common.sh && grep -q 'readonly GCN45_DB_USER="gcn45_qa"' gcn45-common.sh && ok "db name and user are exactly the approved ones" || bad "db name/user differ from the approved ones"
chk "no kill/stop of ports 3000, 5136, 5199 (never a port in a kill command)" '(kill|pkill|killall)[^#]*(3000|5136|5199)'
echo "4. Process termination"
chk "no pkill / killall / kill -9 / kill by lsof" '(pkill|killall|kill[[:space:]]+-9|kill[^#]*lsof)'
grep -q 'case "\$cmd" in \*"\$2"\*)' stop-gcn45-jmeter-env.sh && ok "stop script verifies the command line of every pid before SIGTERM" || bad "stop script has no command-line check"
grep -q 'never stops anything' start-gcn45-jmeter-env.sh && ok "start script refuses busy ports instead of stopping owners" || bad "start script port policy missing"
echo "5. Secret exposure"
chk "no echo/printf of a secret variable" '(echo|printf)[^#|>]*\$\{?(GCN45_JWT_SECRET|GCN45_PAYHERE_SECRET|GCN45_DB_PASSWORD|MYSQL_PWD)'
chk "no set -x / bash -x tracing" '(set[[:space:]]+-[a-z]*x|bash[[:space:]]+-x)'
chk "no secret passed as 'env VAR=...' argument" 'env[[:space:]]+[A-Za-z_]*(SECRET|PASSWORD|Password)'
grep -q 'getconf DARWIN_USER_DIR' gcn45-common.sh && grep -q 'gcn45_assert_outside_git' gcn45-common.sh && ok "secrets live outside every git work tree (guard in code)" || bad "secret location guard missing"
if grep -rEl '[0-9a-f]{40,}' . --include=*.sh --include=*.py --include=*.md --include=*.json >/dev/null 2>&1; then bad "long hex string (possible secret) found in: $(grep -rEl '[0-9a-f]{40,}' . --include=*.sh --include=*.py --include=*.md --include=*.json | tr '\n' ' ')"; else ok "no long hex strings (possible secrets) in scripts, docs or plan metadata"; fi
grep -qE 'GCN45_(JWT|PAYHERE)_SECRET|eyJ' GCN45AppointmentPaymentTest.jmx && grep -qE 'eyJ[A-Za-z0-9_-]{20,}' GCN45AppointmentPaymentTest.jmx && bad "a JWT is embedded in the JMX" || ok "no token or secret value in the JMX (only environment variable names)"
echo "6. JMeter plan targets"
python3 - <<'PY' && ok "plan targets" || bad "plan targets"
import re, sys, xml.etree.ElementTree as ET
t = ET.parse("GCN45AppointmentPaymentTest.jmx"); ports = set(); hosts = set(); n = 0
for e in t.iter("HTTPSamplerProxy"):
    n += 1
    for c in e:
        if c.get("name") == "HTTPSampler.port": ports.add(c.text)
        if c.get("name") == "HTTPSampler.domain": hosts.add(c.text)
print(f"    samplers: {n}; hosts: {sorted(hosts)}; ports: {sorted(ports)}")
sys.exit(0 if hosts == {"localhost"} and ports <= {"5235", "5236", "5237"} else 1)
PY
txt="$(cat GCN45AppointmentPaymentTest.jmx)"; for bad_s in "payhere.lk" "sandbox.payhere" "localhost:5136" "localhost:5199" ":3000/" "carenova_appointment_qa"; do case "$txt" in *"$bad_s"*) bad "plan mentions $bad_s";; *) ok "plan does not mention $bad_s";; esac; done
python3 - <<'PY' && ok "exactly eight scored scenarios JM-01..JM-08 in the plan" || bad "scenario count"
import json
s = json.load(open("scenarios.json"))["scenarios"]; ids = sorted(k for k in s if k.startswith("JM-")); print("    ", ids)
raise SystemExit(0 if ids == [f"JM-0{i}" for i in range(1, 9)] else 1)
PY
grep -q 'KD-D1' GCN45AppointmentPaymentTest.jmx && bad "KD-D1 sample is inside the plan" || ok "KD-D1 is not in the plan"
echo; [ "$FAIL" = 0 ] && echo "ALL CHECKS PASSED" || echo "$FAIL CHECK(S) FAILED"; exit "$FAIL"
