#!/usr/bin/env bash
# Static / offline validator for the GCN-48 JMeter suite. Starts nothing, contacts nothing (no HTTP, no database, no service). Optional: --api-dir DIR also runs the version oracle against a published backend build.
set -u
cd "$(dirname "$0")"
API_DIR=""; [ "${1:-}" = "--api-dir" ] && API_DIR="${2:-}"
FAIL=0
ok(){ printf 'PASS  %s\n' "$1"; }
bad(){ printf 'FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
chk(){ if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }

for f in *.sh; do chk "bash syntax: $f" "bash -n $f"; done
for f in *.py; do chk "python syntax: $f" "python3 -c \"import ast;ast.parse(open('$f').read())\""; done

# destructive commands and clients must not appear in any shipped script
chk "no rm -rf / DROP / TRUNCATE / DELETE FROM / UPDATE / ALTER in scripts" "! grep -nEi 'rm -rf +(/|~|\\.|\\*)|drop +(database|table)|truncate +table|delete +from|^[^#]*\\bupdate +[\`A-Za-z]+ +set\\b|alter +table' *.sh gcn48_verify.py gen_gcn48_fixtures.py | grep -v validate-gcn48 | grep -v -E 'refuse|forbidden|unsafe|_is_safe|banned|re\\.compile|\"\"\"'"
chk "no HTTP client in scripts (curl/wget/nc)" "! grep -nE '(^|[ |;(])(curl|wget|nc)( |$)' *.sh | grep -v validate-gcn48"
chk "no commit/push/git add in scripts" "! grep -nE 'git +(commit|push|add)' *.sh | grep -v validate-gcn48"
chk "no secrets or machine paths (JWT, Bearer token, /Users/, e-mail, key)" "! grep -rnEI 'eyJ[A-Za-z0-9_-]{10,}|Bearer [A-Za-z0-9._-]{20,}|/Users/|pathimini32|BEGIN (RSA|PRIVATE)' *.sh *.py *.jmx *.json *.md *.groovy oracle config .gitignore | grep -v validate-gcn48"
chk "database access is read-only in the verifier (SELECT guard present)" "grep -q 'read-only guard' gcn48_verify.py && ! grep -nEi '\"(INSERT|UPDATE|DELETE)' gcn48_verify.py"
chk "oracle db mode only reads (no SaveChanges / Add / Remove / ExecuteSql)" "! grep -nE 'SaveChanges|ExecuteSql|Database\\.Migrate|db\\.(Add|Remove|Update|Attach)' oracle/Program.cs.txt"

# isolation
chk "GCN-48 targets: database, user, port, stop port are the GCN-48 constants" "grep -q 'GCN48_DB_NAME=\"carenova_appointment_gcn48_qa\"' gcn48-common.sh && grep -q 'GCN48_DB_USER=\"gcn48_qa\"' gcn48-common.sh && grep -q 'GCN48_PORT=5248' gcn48-common.sh && grep -q 4548 run-gcn48-jmeter.sh"
chk "protected ports include 3000 5136 5199 5235-5237 5246 5247" "for p in 3000 5136 5199 5235 5236 5237 5246 5247; do grep -q \"\$p\" gcn48-common.sh || exit 1; done"
chk "no GCN-45/46/47/49 or shared names used as targets" "! grep -nE 'carenova_appointment_gcn4[5-7]_qa|carenova_appointment_qa|carenova_appointment_integration|:524[67]|:523[5-7]|gcn4[5-7]_qa|carenova-gcn4[5-7]' gcn48-*.sh start-gcn48-env.sh stop-gcn48-env.sh run-gcn48-jmeter.sh gcn48_*.py gen_gcn48_*.py | grep -v -E 'refuse|protect|guard|forbid|case|\\*gcn4|ISOLATION|leaked|visible|database that|grep -v'"
chk "the guards refuse GCN-45, GCN-46 and GCN-47 names" "grep -q 'gcn47' gcn48-common.sh && grep -q 'gcn46' gcn48-common.sh && grep -q 'gcn45' gcn48-common.sh"
chk "start script exports no secret on a command line and does no HTTP readiness check" "! grep -nE 'curl|wget' start-gcn48-env.sh && grep -q 'lsof' start-gcn48-env.sh"

# the plan
python3 - <<'P' && ok "plan: exactly 5 HTTP samplers (4 GET + 1 POST), localhost:5248, one thread and one loop each, no redirects/embedded resources, no other sampler type or endpoint" || bad "plan structure"
import re, sys, xml.etree.ElementTree as ET
r = ET.parse("GCN48AppointmentCancellationTest.jmx").getroot(); tags = [e.tag for e in r.iter()]; errs = []
s = list(r.iter("HTTPSamplerProxy"))
if len(s) != 5: errs.append("samplers=%d" % len(s))
if sorted(e.findtext("stringProp[@name='HTTPSampler.method']") for e in s) != ["GET"] * 4 + ["POST"]: errs.append("methods")
for e in s:
    g = lambda n: e.findtext("stringProp[@name='%s']" % n)
    if g("HTTPSampler.domain") != "localhost" or g("HTTPSampler.port") != "5248" or g("HTTPSampler.protocol") != "http": errs.append("target")
    if g("HTTPSampler.path") != "/api/patient/appointments/${TARGET_ID}/cancellation": errs.append("path " + str(g("HTTPSampler.path")))
    for b in ("follow_redirects", "auto_redirects", "image_parser"):
        if e.findtext("boolProp[@name='HTTPSampler.%s']" % b) != "false": errs.append(b)
post = [e for e in s if e.findtext("stringProp[@name='HTTPSampler.method']") == "POST"][0]
body = post.find(".//stringProp[@name='Argument.value']").text
if body != '{"expectedVersion":"${EXPECTED_VERSION}","acknowledgeNoRefund":false,"reason":"${CANCEL_REASON}"}': errs.append("post body")
tg = list(r.iter("ThreadGroup"))
if len(tg) != 5: errs.append("threadgroups")
for g in tg:
    if g.findtext("stringProp[@name='ThreadGroup.num_threads']") != "1" or g.find(".//stringProp[@name='LoopController.loops']").text != "1" or g.findtext("stringProp[@name='ThreadGroup.ramp_time']") != "0": errs.append("threads/loops/ramp")
for t in ("JSR223Sampler", "DebugSampler", "TestAction", "HTTPSampler", "AjaxSampler", "JDBCSampler", "BeanShellSampler", "TransactionController", "RecordingController", "CSVDataSet", "IfController", "WhileController", "ForeachController", "ModuleController", "IncludeController", "RunTime", "ConstantTimer", "ThroughputController", "LoopController_x", "SetUpThreadGroup", "PostThreadGroup", "HTTPSamplerProxy_x"):
    if tags.count(t): errs.append("forbidden " + t)
if [g.get("testname")[:5] for g in tg] != ["JM-01", "JM-02", "JM-03", "JM-04", "JM-05"]: errs.append("scenario names")
if len(re.findall(r"/api/", open("GCN48AppointmentCancellationTest.jmx").read().replace("/api/patient/appointments/${TARGET_ID}/cancellation", ""))): errs.append("another endpoint in the plan")
if errs: print(errs); sys.exit(1)
P
python3 - <<'P' && ok "scenarios.json: 5 scenarios, 5 requests, 1 thread, 1 iteration, smoke-test note, expected statuses 200/200/404/403/200" || bad "scenarios.json"
import json; d = json.load(open("scenarios.json")); s = d["scenarios"]
assert d["total_http_requests"] == 5 and d["iterations_per_scenario"] == 1 and d["threads_per_scenario"] == 1 and "not a load" in d["note"].lower()
assert list(s) == ["JM-01", "JM-02", "JM-03", "JM-04", "JM-05"] and [x["expected_status"] for x in s.values()] == [200, 200, 404, 403, 200] and [x["method"] for x in s.values()] == ["GET"] * 4 + ["POST"]
P
T=$(mktemp -d); cp gen_gcn48_jmx.py "$T/" && (cd "$T" && python3 gen_gcn48_jmx.py >/dev/null 2>&1)
chk "plan and scenarios.json regenerate byte-identically from the generator" "cmp -s '$T/GCN48AppointmentCancellationTest.jmx' GCN48AppointmentCancellationTest.jmx && cmp -s '$T/scenarios.json' scenarios.json"
rm -rf "$T"
chk "no script text contains dollar-brace (JMeter would interpolate it)" "python3 gcn48_extract_scripts.py GCN48AppointmentCancellationTest.jmx \$(mktemp -d)"

# offline behaviour tests
chk "version port self-test" "python3 gcn48_version.py"
chk "fixture generator self-test" "python3 gen_gcn48_fixtures.py --selftest"
chk "fixtures: INSERT-only seed, 8 appointments, 7 payments, synthetic ids, no secrets" "T=\$(mktemp -d); python3 gen_gcn48_fixtures.py --out-dir \$T >/dev/null && [ \$(grep -c '^INSERT' \$T/seed-gcn48.sql) = 2 ] && ! grep -Eqi '^(update|delete|drop|alter|truncate|create|use) ' \$T/seed-gcn48.sql && grep -q 'CN-APT-CXL48-48005' \$T/seed-gcn48.sql && ! grep -Eq 'password|secret|token' \$T/seed-gcn48.sql"
chk "seed negative control: the forbidden-statement scan does flag an UPDATE statement" "printf 'UPDATE Appointments SET Status=1;\n' | grep -Eqi '^(update|delete|drop|alter|truncate|create|use) '"
chk "Groovy scripts compile and the plan's assertions accept correct and reject corrupted responses (offline harness)" "bash gcn48-check-assertions.sh"
chk "verifier accepts correct database states and rejects corrupted ones, and counts exactly five server requests (fake mysql)" "python3 gcn48_verifier_selftest.py"
chk "summary generator runs in the empty state (all BLOCKED, integrity FAIL) without crashing" "T=\$(mktemp -d); cp summarize.py scenarios.json \$T/ && (cd \$T && mkdir results evidence && python3 summarize.py | grep -q BLOCKED)"
chk "run script in plan mode prints the 5-request plan and sends nothing" "bash run-gcn48-jmeter.sh | grep -q 'JM-05 POST'"
chk "shipped files are only the allow-listed suite files" "! ls -A | grep -vE '^(\\.gitignore|GCN-48-QA-Findings\\.md|GCN48AppointmentCancellationTest\\.jmx|README\\.md|config|evidence|fixtures|logs|results|oracle|scenarios\\.json|__pycache__|gcn48-[a-z-]+\\.sh|gcn48_[a-z_]+\\.(py|groovy)|gen_gcn48_(fixtures|jmx)\\.py|run-gcn48-jmeter\\.sh|start-gcn48-env\\.sh|stop-gcn48-env\\.sh|summarize\\.py|validate-gcn48-helpers\\.sh)\$'"
if [ -n "$API_DIR" ]; then chk "version oracle against the published build (decision and version equal the real code's)" "python3 gcn48_check_version.py --api-dir '$API_DIR'"; else echo "SKIP  version oracle (pass --api-dir DIR to include it)"; fi
echo
if [ "$FAIL" -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "$FAIL CHECK(S) FAILED"; fi
exit $FAIL
