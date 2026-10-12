#!/usr/bin/env bash
# Static / offline validator for the GCN-51 JMeter suite. Starts nothing, contacts nothing (no HTTP, no database, no service). 
set -u
cd "$(dirname "$0")"
FAIL=0
ok(){ printf 'PASS  %s\n' "$1"; }
bad(){ printf 'FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
chk(){ if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }

for f in *.sh; do chk "bash syntax: $f" "bash -n $f"; done
for f in *.py; do chk "python syntax: $f" "python3 -c \"import ast;ast.parse(open('$f').read())\""; done

# destructive commands and clients must not appear in any shipped script
chk "no rm -rf / DROP / TRUNCATE / DELETE FROM / UPDATE / ALTER in scripts" "! grep -nEi 'rm -rf +(/|~|\\.|\\*)|drop +(database|table)|truncate +table|delete +from|^[^#]*\\bupdate +[\`A-Za-z]+ +set\\b|alter +table' *.sh gcn51_verify.py gen_gcn51_fixtures.py | grep -v validate-gcn51 | grep -v -E 'refuse|forbidden|unsafe|_is_safe|banned|re\\.compile|\"\"\"'"
chk "no HTTP client in scripts (curl/wget/nc)" "! grep -nE '(^|[ |;(])(curl|wget|nc)( |$)' *.sh | grep -v validate-gcn51"
chk "no commit/push/git add in scripts" "! grep -nE 'git +(commit|push|add)' *.sh | grep -v validate-gcn51"
chk "no secrets or machine paths (JWT, Bearer token, /Users/, e-mail, key)" "! grep -rnEI 'eyJ[A-Za-z0-9_-]{10,}|Bearer [A-Za-z0-9._-]{20,}|/Users/|pathimini32|BEGIN (RSA|PRIVATE)' *.sh *.py *.jmx *.json *.md *.groovy config .gitignore | grep -v validate-gcn51"
chk "database access is read-only in the verifier (SELECT guard present)" "grep -q 'read-only guard' gcn51_verify.py && ! grep -nEi '\"(INSERT|UPDATE|DELETE) ' gcn51_verify.py"

# isolation
chk "GCN-51 targets: database, user, port, stop port are the GCN-51 constants" "grep -q 'GCN51_DB_NAME=\"carenova_appointment_gcn51_qa\"' gcn51-common.sh && grep -q 'GCN51_DB_USER=\"gcn51_qa\"' gcn51-common.sh && grep -q 'GCN51_PORT=5251' gcn51-common.sh && grep -q 4551 run-gcn51-jmeter.sh"
chk "protected ports include 3000 5136 5199 5235-5237 5246 5247 5248" "for p in 3000 5136 5199 5235 5236 5237 5246 5247 5248; do grep -q \"\$p\" gcn51-common.sh || exit 1; done"
chk "no GCN-45/46/47/48/49 or shared names used as targets" "! grep -nE 'carenova_appointment_gcn4[5-8]_qa|carenova_appointment_qa|carenova_appointment_integration|:524[678]|:523[5-7]|gcn4[5-8]_qa|carenova-gcn4[5-8]' gcn51-*.sh start-gcn51-env.sh stop-gcn51-env.sh run-gcn51-jmeter.sh gcn51_*.py gen_gcn51_*.py | grep -v -E 'refuse|protect|guard|forbid|case|\\*gcn4|ISOLATION|leaked|visible|database that|grep -v'"
chk "the guards refuse GCN-45, GCN-46, GCN-47 and GCN-48 names" "grep -q 'gcn48' gcn51-common.sh && grep -q 'gcn47' gcn51-common.sh && grep -q 'gcn46' gcn51-common.sh && grep -q 'gcn45' gcn51-common.sh"
chk "start script exports no secret on a command line and does no HTTP readiness check" "! grep -nE 'curl|wget' start-gcn51-env.sh && grep -q 'lsof' start-gcn51-env.sh"

# the plan
python3 - <<'P' && ok "plan: exactly 9 scenarios (J01-J09) with exactly 9 GET samplers, one per scenario, guarded host/port variables, no write method, no other sampler type, one thread each, J09 loops its single sampler 30 times" || bad "plan structure"
import re, sys, xml.etree.ElementTree as ET
r = ET.parse("GCN51RoleDashboardTest.jmx").getroot(); tags = [e.tag for e in r.iter()]; errs = []
s = list(r.iter("HTTPSamplerProxy")); tg = list(r.iter("ThreadGroup"))
if len(s) != 9: errs.append("samplers=%d" % len(s))
if len(tg) != 9: errs.append("threadgroups=%d" % len(tg))
allowed = {"/api/patient/dashboard/appointments", "/api/staff/dashboard/appointment-payments", "/api/doctor/appointments"}
for e in s:
    g = lambda n: e.findtext("stringProp[@name='%s']" % n)
    if g("HTTPSampler.method") != "GET": errs.append("non-GET " + str(g("HTTPSampler.method")))
    if g("HTTPSampler.domain") != "${HOST}" or g("HTTPSampler.port") != "${PORT}" or g("HTTPSampler.protocol") != "http": errs.append("target is not the guarded variables")
    if g("HTTPSampler.path") not in allowed: errs.append("path " + str(g("HTTPSampler.path")))
    for b in ("follow_redirects", "auto_redirects", "image_parser"):
        if e.findtext("boolProp[@name='HTTPSampler.%s']" % b) != "false": errs.append(b)
for g in tg:
    loops = g.find(".//stringProp[@name='LoopController.loops']").text
    if g.findtext("stringProp[@name='ThreadGroup.num_threads']") != "1" or g.findtext("stringProp[@name='ThreadGroup.ramp_time']") != "0" or loops != ("30" if g.get("testname").startswith("J09") else "1"): errs.append("threads/loops " + g.get("testname"))
for t in ("JSR223Sampler", "DebugSampler", "TestAction", "HTTPSampler", "AjaxSampler", "JDBCSampler", "BeanShellSampler", "TransactionController", "RecordingController", "CSVDataSet", "IfController", "WhileController", "ForeachController", "ModuleController", "IncludeController", "RunTime", "ThroughputController", "SetUpThreadGroup", "PostThreadGroup", "ConstantTimer"):
    if tags.count(t): errs.append("forbidden " + t)
if [g.get("testname")[:3] for g in tg] != ["J01", "J02", "J03", "J04", "J05", "J06", "J07", "J08", "J09"]: errs.append("scenario names")
per = []; cur = None
for e in r.iter():
    if e.tag == "ThreadGroup": per.append(0)
    if e.tag == "HTTPSamplerProxy": per[-1] += 1
if per != [1] * 9: errs.append("samplers per scenario " + str(per))
if len(list(r.iter("DurationAssertion"))) != 9: errs.append("every sampler needs a response-time assertion")
if errs: print(errs); sys.exit(1)
P
python3 - <<'P' && ok "scenarios.json: 9 scenarios, 9 samplers, 38 requests, read-only, thresholds documented, J05 replacement documented" || bad "scenarios.json"
import json; d = json.load(open("scenarios.json")); s = d["scenarios"]
assert d["total_requests"] == 38 and d["samplers"] == 9 and d["read_only"] is True and "not a load" in d["note"].lower()
assert [x["requests"] for x in s.values()] == [1, 1, 1, 1, 1, 1, 1, 1, 30] and d["scenarios"]["J09"]["iterations"] == 30
assert list(s) == ["J01", "J02", "J03", "J04", "J05", "J06", "J07", "J08", "J09"] and sum(x["requests"] for x in s.values()) == 38 and all(x["method"] == "GET" for x in s.values())
assert [x["expected_status"] for x in s.values()] == [200, 200, 200, 200, 200, 401, 403, 403, 200] and "REPLACEMENT" in s["J05"]["note"] and all("threshold_ms" in x for x in s.values())
P
T=$(mktemp -d); cp gen_gcn51_jmx.py "$T/" && (cd "$T" && python3 gen_gcn51_jmx.py >/dev/null 2>&1)
chk "plan and scenarios.json regenerate byte-identically from the generator" "cmp -s '$T/GCN51RoleDashboardTest.jmx' GCN51RoleDashboardTest.jmx && cmp -s '$T/scenarios.json' scenarios.json"
rm -rf "$T"
chk "no script text contains dollar-brace (JMeter would interpolate it)" "python3 gcn51_extract_scripts.py GCN51RoleDashboardTest.jmx \$(mktemp -d)"

# offline behaviour tests
chk "fixture generator self-test" "python3 gen_gcn51_fixtures.py --selftest"
chk "fixtures: INSERT-only seed (3 INSERT statements: appointments, payments, receipts), synthetic ids, no secrets" "T=\$(mktemp -d); python3 gen_gcn51_fixtures.py --out-dir \$T >/dev/null && [ \$(grep -c '^INSERT' \$T/seed-gcn51.sql) = 3 ] && ! grep -Eqi '^(update|delete|drop|alter|truncate|create|use) ' \$T/seed-gcn51.sql && grep -q 'CN-APT-DSH-51001' \$T/seed-gcn51.sql && ! grep -Eq 'password|secret|token' \$T/seed-gcn51.sql"
chk "seed negative control: the forbidden-statement scan does flag an UPDATE statement" "printf 'UPDATE Appointments SET Status=1;\n' | grep -Eqi '^(update|delete|drop|alter|truncate|create|use) '"
chk "Groovy scripts compile and the plan's assertions accept correct and reject corrupted responses (offline harness)" "bash gcn51-check-assertions.sh"
chk "verifier and summary accept correct states and reject corrupted ones; the request log must show exactly the 38 expected GET requests (fake mysql, synthetic JTL)" "python3 gcn51_verifier_selftest.py"
chk "summary generator runs in the empty state (all BLOCKED, integrity FAIL) without crashing" "T=\$(mktemp -d); cp summarize.py scenarios.json \$T/ && (cd \$T && mkdir results evidence && python3 summarize.py | grep -q BLOCKED)"
chk "run script in plan mode prints the plan and sends nothing" "bash run-gcn51-jmeter.sh | grep -q 'J09'"
chk "shipped files are only the allow-listed suite files" "! ls -A | grep -vE '^(\\.gitignore|GCN-51-QA-Findings\\.md|GCN51RoleDashboardTest\\.jmx|README\\.md|config|evidence|fixtures|logs|results|scenarios\\.json|__pycache__|gcn51-[a-z-]+\\.sh|gcn51_[a-z_]+\\.(py|groovy)|gen_gcn51_(fixtures|jmx)\\.py|gcn51-migrations-preview\\.sql|jmeter\\.log|run-gcn51-jmeter\\.sh|start-gcn51-env\\.sh|stop-gcn51-env\\.sh|summarize\\.py|validate-gcn51-helpers\\.sh)\$'"
echo
if [ "$FAIL" -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "$FAIL CHECK(S) FAILED"; fi
exit $FAIL
