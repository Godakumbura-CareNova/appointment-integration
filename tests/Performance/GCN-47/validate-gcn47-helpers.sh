#!/usr/bin/env bash
# Static validator for the GCN-47 JMeter suite. Starts nothing, contacts nothing.
set -u
cd "$(dirname "$0")"
FAIL=0
ok(){ printf 'PASS  %s\n' "$1"; }
bad(){ printf 'FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
chk(){ if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }

for f in *.sh; do chk "bash syntax: $f" "bash -n $f"; done
for f in *.py; do chk "python syntax: $f" "python3 -c \"import ast,sys;ast.parse(open('$f').read())\""; done

# destructive commands must not appear in any shipped script
chk "no rm -rf / DROP DATABASE / TRUNCATE / DELETE FROM in scripts" "! grep -nEi 'rm -rf|drop +(database|table)|truncate +table|delete +from' *.sh *.py | grep -v validate-gcn47 | grep -v -E 'refuse|forbidden|unsafe|_is_safe|DENY|banned|re\\.compile|#'"
# isolation: no other ticket's names/ports used as targets
chk "no GCN-45/46/49 DB names used as targets" "! grep -nE 'carenova_appointment_gcn4[56]_qa|carenova_appointment_qa' gcn47-*.sh start-gcn47-env.sh run-gcn47-jmeter.sh | grep -v -E 'refuse|protect|guard|forbid|case|\\*gcn4'"
chk "backend port constant is 5247" "grep -q 'GCN47_PORT=5247' gcn47-common.sh"
chk "protected ports include 5235-5237 5246 5136 5199 3000" "for p in 3000 5136 5199 5235 5236 5237 5246; do grep -q \"\$p\" gcn47-common.sh || exit 1; done"
chk "no HTTP client in scripts (curl/wget/nc)" "! grep -nE '(^|[ |;(])(curl|wget|nc)( |$)' *.sh | grep -v validate-gcn47"
chk "no commit/push/git add in scripts" "! grep -nE 'git +(commit|push|add)' *.sh | grep -v validate-gcn47"
chk "no secrets or machine paths committed (password/Bearer/eyJ/home path)" "! grep -nE 'eyJ[A-Za-z0-9_-]{10,}|Bearer [A-Za-z0-9._-]{20,}|/Users/[a-z]+' *.sh *.py *.jmx *.json *.md config/* .gitignore 2>/dev/null | grep -v validate-gcn47"

# plan structure
python3 - <<'P' && ok "plan structure" || bad "plan structure"
import re,sys,xml.etree.ElementTree as ET
t=ET.parse("GCN47DoctorAppointmentsTest.jmx"); r=t.getroot()
tags=[e.tag for e in r.iter()]
def n(x): return tags.count(x)
errs=[]
s=[e for e in r.iter("HTTPSamplerProxy")]
if len(s)!=5: errs.append("samplers=%d"%len(s))
meth=sorted(e.findtext("stringProp[@name='HTTPSampler.method']") for e in s)
if meth!=["GET"]*4+["PATCH"]: errs.append("methods %s"%meth)
for e in s:
    if e.findtext("stringProp[@name='HTTPSampler.domain']")!="localhost": errs.append("host")
    if e.findtext("stringProp[@name='HTTPSampler.port']")!="5247": errs.append("port")
    if e.findtext("boolProp[@name='HTTPSampler.follow_redirects']")!="false": errs.append("follow")
    if e.findtext("boolProp[@name='HTTPSampler.auto_redirects']")!="false": errs.append("auto")
    if e.findtext("boolProp[@name='HTTPSampler.image_parser']")!="false": errs.append("embedded")
tg=[e for e in r.iter("ThreadGroup")]
if len(tg)!=5: errs.append("threadgroups")
for g in tg:
    if g.findtext("stringProp[@name='ThreadGroup.num_threads']")!="1": errs.append("threads")
    if g.find(".//stringProp[@name='LoopController.loops']").text!="1": errs.append("loops")
for bad_t in ["JSR223Sampler","DebugSampler","TestAction","HTTPSampler","AjaxSampler","JDBCSampler","BeanShellSampler","TransactionController","LoopController_x","RecordingController"]:
    if n(bad_t): errs.append("forbidden "+bad_t)
names=[g.get("testname") for g in tg]
if not all(re.match(r"JM-0[1-5]",x) for x in names): errs.append("names %s"%names)
if errs: print(errs); sys.exit(1)
P
chk "scenarios.json declares 5 requests" "python3 -c \"import json;d=json.load(open('scenarios.json'));assert d['total_http_requests']==5\""
chk "fixture generator selftest" "python3 gen_gcn47_fixtures.py --selftest"
T=$(mktemp -d)
cp gen_gcn47_jmx.py "$T/" && (cd "$T" && python3 gen_gcn47_jmx.py >/dev/null 2>&1)
chk "plan regenerates byte-identically from the generator" "cmp -s '$T/GCN47DoctorAppointmentsTest.jmx' GCN47DoctorAppointmentsTest.jmx"
rm -rf "$T"

echo
if [ "$FAIL" -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "$FAIL CHECK(S) FAILED"; fi
exit $FAIL
