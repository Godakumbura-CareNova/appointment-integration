#!/usr/bin/env bash
# Offline validator for the GCN-53 six-request suite. Starts nothing, contacts nothing (no HTTP, no database, no service).
set -u
cd "$(dirname "$0")"
FAIL=0
ok(){ printf 'PASS  %s\n' "$1"; }
bad(){ printf 'FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
chk(){ if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }
for f in *.sh; do chk "bash syntax: $f" "bash -n $f"; done
for f in *.py; do chk "python syntax: $f" "python3 -c \"import ast;ast.parse(open('$f').read())\""; done
chk "no HTTP client, commit/push or destructive command in the scripts" "! grep -nE '(^|[ |;(])(curl|wget|nc)( |\$)|git +(commit|push|add)|rm -rf +(/|~|\\.|\\*)|drop +(database|table)' *.sh *.py | grep -v validate-gcn53-six"
chk "no secrets or machine paths (JWT, Bearer token, /Users/, e-mail, key)" "! grep -rnEI 'eyJ[A-Za-z0-9_-]{10,}|Bearer [A-Za-z0-9._-]{20,}|/Users/|pathimini32|BEGIN (RSA|PRIVATE)' . | grep -v validate-gcn53-six"
chk "results go to the six-request folder (jmeter-six), never to the 66-request results folder" "grep -q 'jmeter-six' run-gcn53-six.sh && grep -q 'jmeter-six' gcn53-six-preflight.sh && grep -q 'jmeter-six' summarize_six.py && ! grep -nE 'GCN-53/jmeter[\"/ ]' *.sh *.py | grep -v jmeter-six | grep -v validate-gcn53-six"
chk "the target is the isolated GCN-53 environment only (port 5253, stop port 4553)" "grep -q 5253 run-gcn53-six.sh && grep -q 4553 run-gcn53-six.sh && ! grep -nE '5251|5248|5247|5246' run-gcn53-six.sh gcn53-six-preflight.sh gcn53_six_requests.py"
python3 - <<'P' && ok "plan: exactly 6 test cases (T01-T06), exactly 6 HTTP GET samplers (one per case), one thread, one iteration, no loops, guarded host/port variables, only allowed admin endpoints, no other sampler type" || bad "plan structure"
import sys, xml.etree.ElementTree as ET
r = ET.parse("GCN53AdminDashboardSixTest.jmx").getroot(); tags = [e.tag for e in r.iter()]; errs = []
s = list(r.iter("HTTPSamplerProxy")); tg = list(r.iter("ThreadGroup"))
if len(s) != 6: errs.append("samplers=%d" % len(s))
if len(tg) != 6: errs.append("threadgroups=%d" % len(tg))
allowed = ("/api/admin/dashboard/appointments", "/api/admin/dashboard/appointment-payments", "/api/admin/appointments", "/api/admin/reports/appointment-income")
for e in s:
    g = lambda n: e.findtext("stringProp[@name='%s']" % n)
    if g("HTTPSampler.method") != "GET": errs.append("non-GET")
    if g("HTTPSampler.domain") != "${HOST}" or g("HTTPSampler.port") != "${PORT}" or g("HTTPSampler.protocol") != "http": errs.append("target is not the guarded variables")
    if g("HTTPSampler.path").split("?")[0] not in allowed: errs.append("path " + g("HTTPSampler.path"))
    for b in ("follow_redirects", "auto_redirects", "image_parser"):
        if e.findtext("boolProp[@name='HTTPSampler.%s']" % b) != "false": errs.append(b)
for g in tg:
    if g.findtext("stringProp[@name='ThreadGroup.num_threads']") != "1" or g.findtext("stringProp[@name='ThreadGroup.ramp_time']") != "0" or g.find(".//stringProp[@name='LoopController.loops']").text != "1": errs.append("threads/loops " + g.get("testname"))
for t in ("JSR223Sampler", "DebugSampler", "TestAction", "HTTPSampler", "TransactionController", "CSVDataSet", "IfController", "WhileController", "ForeachController", "LoopController_x", "ModuleController", "IncludeController", "RunTime", "ThroughputController", "SetUpThreadGroup", "PostThreadGroup", "ConstantTimer"):
    if tags.count(t): errs.append("forbidden " + t)
if [g.get("testname")[:3] for g in tg] != ["T01", "T02", "T03", "T04", "T05", "T06"]: errs.append("names")
per = []
for e in r.iter():
    if e.tag == "ThreadGroup": per.append(0)
    if e.tag == "HTTPSamplerProxy": per[-1] += 1
if per != [1] * 6: errs.append("samplers per case " + str(per))
if len(list(r.iter("DurationAssertion"))) != 6: errs.append("response-time assertions")
if errs: print(errs); sys.exit(1)
P
python3 - <<'P' && ok "scenarios.json: 6 test cases, 6 samplers, 6 requests, one iteration each, read-only, expected statuses 200/200/200/200/401/403" || bad "scenarios.json"
import json; d = json.load(open("scenarios.json")); s = d["scenarios"]
assert d["total_requests"] == 6 and d["samplers"] == 6 and d["test_cases"] == 6 and d["iterations_per_case"] == 1 and d["read_only"] is True and "not a load" in d["note"].lower()
assert list(s) == ["T01", "T02", "T03", "T04", "T05", "T06"] and all(x["requests"] == 1 and x["method"] == "GET" for x in s.values()) and [x["expected_status"] for x in s.values()] == [200, 200, 200, 200, 401, 403]
P
T=$(mktemp -d); cp gen_gcn53_six_jmx.py "$T/" && mkdir "$T/../_six_parent_$$" 2>/dev/null; rm -rf "$T/../_six_parent_$$"
chk "plan and scenarios.json regenerate byte-identically from the generator" "T2=\$(mktemp -d) && mkdir -p \$T2/six && cp gen_gcn53_six_jmx.py \$T2/six/ && cp ../gen_gcn53_jmx.py \$T2/ && (cd \$T2/six && python3 gen_gcn53_six_jmx.py >/dev/null) && cmp -s \$T2/six/GCN53AdminDashboardSixTest.jmx GCN53AdminDashboardSixTest.jmx && cmp -s \$T2/six/scenarios.json scenarios.json"
rm -rf "$T"
# the assertion scripts are the ALREADY VALIDATED ones of the 66-request plan: byte-identical, case by case
python3 - <<'P' && ok "all 18 Groovy scripts (pre-processor, environment check, value/denial assertion per case) are byte-identical to the already-validated scripts of the 66-request plan (T01=J01a, T02=J01b, T03=J02b, T04=J03a, T05=J04b, T06=J05c)" || bad "assertion scripts differ from the validated ones"
import xml.etree.ElementTree as ET
def scripts(path):
    out = {}; cur = None; k = -1
    for e in ET.parse(path).getroot().iter():
        if e.tag == "HTTPSamplerProxy": cur = e.get("testname").split()[0]; out[cur] = {"path": e.findtext("stringProp[@name='HTTPSampler.path']"), "scripts": [], "asserts": []}
        elif cur and e.tag in ("JSR223PreProcessor", "JSR223Assertion"): out[cur]["scripts"].append((e.tag, e.get("testname"), e.findtext("stringProp[@name='script']")))
        elif cur and e.tag in ("ResponseAssertion", "DurationAssertion"): out[cur]["asserts"].append(ET.tostring(e))
    return out
six = scripts("GCN53AdminDashboardSixTest.jmx"); par = scripts("../GCN53AdminDashboardTest.jmx")
# the six plan's samplers are labelled T01 ..: map by position of the sampler in the parent plan
pmap = {"T01": "J01a", "T02": "J01b", "T03": "J02b", "T04": "J03a", "T05": "J04b", "T06": "J05c"}
bad = []
for t, j in pmap.items():
    a, b = six[t], par[j]
    if a["path"] != b["path"] or a["scripts"] != b["scripts"]: bad.append(t)
    if [x for x in a["asserts"]] != [x for x in b["asserts"]]: bad.append(t + " assertions")
if bad: print(bad); raise SystemExit(1)
P
chk "all 18 Groovy scripts compile" "T3=\$(mktemp -d); LIB=\$(brew --prefix jmeter)/libexec/lib; JAVA=\$(brew --prefix openjdk@21)/bin/java; [ -x \$JAVA ] || JAVA=\$(command -v java); CP=\$(ls \$LIB/groovy*-3.*.jar | tr '\n' ':'); python3 ../gcn53_extract_scripts.py GCN53AdminDashboardSixTest.jmx \$T3 | grep -q '18 scripts' && for f in \$T3/*.groovy; do \$JAVA -cp \"\$CP\" groovy.ui.GroovyMain -e \"new GroovyShell().parse(new File('\$f'))\" || exit 1; done"
chk "request-log check and report accept the correct run and reject corrupted ones (synthetic logs and JTL)" "python3 gcn53_six_selftest.py"
chk "run script in plan mode prints the six requests and sends nothing" "bash run-gcn53-six.sh | grep -c 'T0[1-6] GET' | grep -q 6"
chk "the suite folder holds only the allow-listed source files" "! ls -A | grep -vE '^(GCN53AdminDashboardSixTest\\.jmx|README\\.md|scenarios\\.json|__pycache__|gen_gcn53_six_jmx\\.py|gcn53-six-preflight\\.sh|gcn53_six_requests\\.py|gcn53_six_selftest\\.py|run-gcn53-six\\.sh|summarize_six\\.py|validate-gcn53-six\\.sh)\$'"
echo
if [ "$FAIL" -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "$FAIL CHECK(S) FAILED"; fi
exit $FAIL
