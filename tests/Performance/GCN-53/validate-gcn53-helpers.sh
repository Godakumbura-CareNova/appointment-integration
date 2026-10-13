#!/usr/bin/env bash
# Static / offline validator for the GCN-53 JMeter suite. Starts nothing, contacts nothing (no HTTP, no database, no service). 
set -u
cd "$(dirname "$0")"
FAIL=0
ok(){ printf 'PASS  %s\n' "$1"; }
bad(){ printf 'FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
chk(){ if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }

for f in *.sh; do chk "bash syntax: $f" "bash -n $f"; done
for f in *.py; do chk "python syntax: $f" "python3 -c \"import ast;ast.parse(open('$f').read())\""; done

# destructive commands and clients must not appear in any shipped script
chk "no rm -rf / DROP / TRUNCATE / DELETE FROM / UPDATE / ALTER in scripts" "! grep -nEi 'rm -rf +(/|~|\\.|\\*)|drop +(database|table)|truncate +table|delete +from|^[^#]*\\bupdate +[\`A-Za-z]+ +set\\b|alter +table' *.sh gcn53_verify.py gen_gcn53_fixtures.py | grep -v validate-gcn53 | grep -v -E 'refuse|forbidden|unsafe|_is_safe|banned|re\\.compile|\"\"\"'"
chk "no HTTP client in scripts (curl/wget/nc)" "! grep -nE '(^|[ |;(])(curl|wget|nc)( |$)' *.sh | grep -v validate-gcn53"
chk "no commit/push/git add in scripts" "! grep -nE 'git +(commit|push|add)' *.sh | grep -v validate-gcn53"
chk "no secrets or machine paths (JWT, Bearer token, /Users/, e-mail, key)" "! grep -rnEI 'eyJ[A-Za-z0-9_-]{10,}|Bearer [A-Za-z0-9._-]{20,}|/Users/|pathimini32|BEGIN (RSA|PRIVATE)' *.sh *.py *.jmx *.json *.md *.groovy config .gitignore | grep -v validate-gcn53"
chk "database access is read-only in the verifier (SELECT guard present)" "grep -q 'read-only guard' gcn53_verify.py && ! grep -nEi '\"(INSERT|UPDATE|DELETE) ' gcn53_verify.py"

# isolation
chk "GCN-53 targets: database, user, port, stop port are the GCN-53 constants" "grep -q 'GCN53_DB_NAME=\"carenova_appointment_gcn53_qa\"' gcn53-common.sh && grep -q 'GCN53_DB_USER=\"gcn53_qa\"' gcn53-common.sh && grep -q 'GCN53_PORT=5253' gcn53-common.sh && grep -q 4553 run-gcn53-jmeter.sh"
chk "protected ports include 3000 5136 5199 5235-5237 5246 5247 5248 5251" "for p in 3000 5136 5199 5235 5236 5237 5246 5247 5248 5251; do grep -q \"\$p\" gcn53-common.sh || exit 1; done"
chk "no GCN-45/46/47/48/49/51 or shared names used as targets" "! grep -nE 'carenova_appointment_gcn4[5-8]_qa|carenova_appointment_gcn51_qa|carenova_appointment_qa|carenova_appointment_integration|:5251|:524[678]|:523[5-7]|gcn4[5-8]_qa|gcn51_qa|carenova-gcn4[5-8]|carenova-gcn51' gcn53-*.sh start-gcn53-env.sh stop-gcn53-env.sh run-gcn53-jmeter.sh gcn53_*.py gen_gcn53_*.py | grep -v -E 'refuse|protect|guard|forbid|case|\\*gcn4|ISOLATION|leaked|visible|database that|grep -v'"
chk "the guards refuse GCN-45, GCN-46, GCN-47, GCN-48 and GCN-51 names" "grep -q 'gcn51' gcn53-common.sh && grep -q 'gcn48' gcn53-common.sh && grep -q 'gcn47' gcn53-common.sh && grep -q 'gcn46' gcn53-common.sh && grep -q 'gcn45' gcn53-common.sh"
chk "start script exports no secret on a command line and does no HTTP readiness check" "! grep -nE 'curl|wget' start-gcn53-env.sh && grep -q 'lsof' start-gcn53-env.sh"

# the plan
python3 - <<'P' && ok "plan: exactly 6 logical scenarios (J01-J06), 24 GET samplers (2/5/2/4/8/3), guarded host/port variables, only the four admin endpoints, no write method, no other sampler type, one thread each, J06 loops 15 times" || bad "plan structure"
import re, sys, xml.etree.ElementTree as ET
r = ET.parse("GCN53AdminDashboardTest.jmx").getroot(); tags = [e.tag for e in r.iter()]; errs = []
s = list(r.iter("HTTPSamplerProxy")); tg = list(r.iter("ThreadGroup"))
if len(s) != 24: errs.append("samplers=%d" % len(s))
if len(tg) != 6: errs.append("threadgroups=%d" % len(tg))
allowed = ("/api/admin/dashboard/appointments", "/api/admin/dashboard/appointment-payments", "/api/admin/appointments", "/api/admin/reports/appointment-income")
for e in s:
    g = lambda n: e.findtext("stringProp[@name='%s']" % n)
    if g("HTTPSampler.method") != "GET": errs.append("non-GET " + str(g("HTTPSampler.method")))
    if g("HTTPSampler.domain") != "${HOST}" or g("HTTPSampler.port") != "${PORT}" or g("HTTPSampler.protocol") != "http": errs.append("target is not the guarded variables")
    path = g("HTTPSampler.path")
    if path.split("?")[0] not in allowed: errs.append("path " + str(path))
    for b in ("follow_redirects", "auto_redirects", "image_parser"):
        if e.findtext("boolProp[@name='HTTPSampler.%s']" % b) != "false": errs.append(b)
for g in tg:
    loops = g.find(".//stringProp[@name='LoopController.loops']").text
    if g.findtext("stringProp[@name='ThreadGroup.num_threads']") != "1" or g.findtext("stringProp[@name='ThreadGroup.ramp_time']") != "0" or loops != ("15" if g.get("testname").startswith("J06") else "1"): errs.append("threads/loops " + g.get("testname"))
for t in ("JSR223Sampler", "DebugSampler", "TestAction", "HTTPSampler", "AjaxSampler", "JDBCSampler", "BeanShellSampler", "TransactionController", "RecordingController", "CSVDataSet", "IfController", "WhileController", "ForeachController", "ModuleController", "IncludeController", "RunTime", "ThroughputController", "SetUpThreadGroup", "PostThreadGroup", "ConstantTimer"):
    if tags.count(t): errs.append("forbidden " + t)
if [g.get("testname")[:3] for g in tg] != ["J01", "J02", "J03", "J04", "J05", "J06"]: errs.append("scenario names")
per = []
for e in r.iter():
    if e.tag == "ThreadGroup": per.append(0)
    if e.tag == "HTTPSamplerProxy": per[-1] += 1
if per != [2, 5, 2, 4, 8, 3]: errs.append("samplers per scenario " + str(per))
if len(list(r.iter("DurationAssertion"))) != 24: errs.append("every sampler needs a response-time assertion")
if errs: print(errs); sys.exit(1)
P
python3 - <<'P' && ok "scenarios.json: 6 scenarios, 24 samplers, 66 requests, read-only, thresholds documented" || bad "scenarios.json"
import json; d = json.load(open("scenarios.json")); s = d["scenarios"]
assert d["total_requests"] == 66 and d["samplers"] == 24 and d["scenarios_count"] == 6 and d["read_only"] is True and "not a load" in d["note"].lower()
assert list(s) == ["J01", "J02", "J03", "J04", "J05", "J06"] and [x["samplers"] for x in s.values()] == [2, 5, 2, 4, 8, 3] and [x["requests"] for x in s.values()] == [2, 5, 2, 4, 8, 45]
assert all("threshold_ms" in x for x in s.values()) and s["J06"]["iterations"] == 15 and s["J06"]["mean_threshold_ms"] == 400 and s["J06"]["p95_threshold_ms"] == 750
P
T=$(mktemp -d); cp gen_gcn53_jmx.py "$T/" && (cd "$T" && python3 gen_gcn53_jmx.py >/dev/null 2>&1)
chk "plan and scenarios.json regenerate byte-identically from the generator" "cmp -s '$T/GCN53AdminDashboardTest.jmx' GCN53AdminDashboardTest.jmx && cmp -s '$T/scenarios.json' scenarios.json"
rm -rf "$T"
chk "no script text contains dollar-brace (JMeter would interpolate it)" "python3 gcn53_extract_scripts.py GCN53AdminDashboardTest.jmx \$(mktemp -d)"

# offline behaviour tests
chk "fixture generator self-test" "python3 gen_gcn53_fixtures.py --selftest"
chk "fixtures: INSERT-only seed (3 INSERT statements: appointments, payments, receipts), synthetic ids, no secrets" "T=\$(mktemp -d); python3 gen_gcn53_fixtures.py --out-dir \$T >/dev/null && [ \$(grep -c '^INSERT' \$T/seed-gcn53.sql) = 3 ] && ! grep -Eqi '^(update|delete|drop|alter|truncate|create|use) ' \$T/seed-gcn53.sql && grep -q 'CN-APT-ADM-53001' \$T/seed-gcn53.sql && ! grep -Eq 'password|secret|token' \$T/seed-gcn53.sql"
chk "seed negative control: the forbidden-statement scan does flag an UPDATE statement" "printf 'UPDATE Appointments SET Status=1;\n' | grep -Eqi '^(update|delete|drop|alter|truncate|create|use) '"
chk "Groovy scripts compile and the plan's assertions accept correct and reject corrupted responses (offline harness)" "bash gcn53-check-assertions.sh"
chk "verifier and summary accept correct states and reject corrupted ones; the request log must show exactly the 66 expected GET requests (fake mysql, synthetic JTL)" "python3 gcn53_verifier_selftest.py"
chk "summary generator runs in the empty state (all BLOCKED, integrity FAIL) without crashing" "T=\$(mktemp -d); cp summarize.py scenarios.json \$T/ && (cd \$T && mkdir results evidence && python3 summarize.py | grep -q BLOCKED)"
chk "run script in plan mode prints the plan and sends nothing" "bash run-gcn53-jmeter.sh | grep -q 'J06'"
chk "shipped files are only the allow-listed suite files" "! ls -A | grep -vE '^(\\.gitignore|GCN-53-QA-Findings\\.md|GCN53AdminDashboardTest\\.jmx|README\\.md|config|six|scenarios\\.json|__pycache__|gcn53-[a-z-]+\\.sh|gcn53_[a-z_]+\\.(py|groovy)|gen_gcn53_(fixtures|jmx)\\.py|run-gcn53-jmeter\\.sh|start-gcn53-env\\.sh|stop-gcn53-env\\.sh|summarize\\.py|validate-gcn53-helpers\\.sh)\$'"
echo
if [ "$FAIL" -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "$FAIL CHECK(S) FAILED"; fi
exit $FAIL
