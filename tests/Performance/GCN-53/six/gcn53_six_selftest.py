#!/usr/bin/env python3
"""Offline self-test of gcn53_six_requests.py and summarize_six.py with synthetic backend logs and JTL files (no database, no server, no network): they must ACCEPT the correct six-request run and
REJECT every deliberately corrupted one. Exit 1 if any case behaves differently from what is expected."""
import csv, json, os, shutil, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); T = tempfile.mkdtemp(prefix="gcn53-six-test-"); OUT = os.path.join(T, "out")
for d in ("evidence", "logs", "results/run"): os.makedirs(os.path.join(OUT, d))
ENV = {**os.environ, "GCN53_OUT": OUT}; wrong = 0
def run(script): r = subprocess.run([sys.executable, os.path.join(HERE, script)], capture_output=True, text=True, env=ENV); return r.returncode, r.stdout
def expect(name, script, ok):
    global wrong; rc, out = run(script); good = (rc == 0) == ok; wrong += not good
    fails = [l.strip()[6:90] for l in out.splitlines() if l.strip().startswith("FAIL")][:1]
    print(("OK    " if good else "WRONG ") + f"{script[:22]:22} {name:76}" + (" -> rejected: " + fails[0] if rc and fails else (" -> accepted" if rc == 0 else " -> rejected")))
DA, DP, AL, RP = "/api/admin/dashboard/appointments", "/api/admin/dashboard/appointment-payments", "/api/admin/appointments", "/api/admin/reports/appointment-income"
GOOD = [(DA, 200), (DP, 200), (AL, 200), (RP, 200), (DP, 401), (AL, 403)]
open(os.path.join(OUT, "evidence", "log-baseline.txt"), "w").write("8"); pre = ["info: startup"] * 8
def lines(m, p, st): return [f"      Request starting HTTP/1.1 {m} http://localhost:5253{p} - - -", f"      Request finished HTTP/1.1 {m} http://localhost:5253{p} - {st} - application/json;+charset=utf-8 5.0ms"]
def log(reqs, name, ok, method="GET"):
    open(os.path.join(OUT, "logs", "backend.log"), "w").write("\n".join(pre + sum((lines(method, p, s) for p, s in reqs), [])) + "\n"); expect(name, "gcn53_six_requests.py", ok)
print("-- the backend's own request log --")
log(GOOD, "exactly the six expected requests", True)
log(GOOD + [("/health", 200)], "a seventh request (health check)", False)
log(GOOD[:-1], "only five requests", False)
log(GOOD + [GOOD[-1]], "the last request repeated (retry)", False)
log(GOOD[:2] + [GOOD[3], GOOD[2]] + GOOD[4:], "list and report swapped (order matters)", False)
log(GOOD[:4] + [(DP, 200), (AL, 403)], "T05 answered 200 instead of 401", False)
log(GOOD[:5] + [(AL, 401)], "T06 answered 401 instead of 403", False)
log(GOOD[:3] + [(RP, 500)] + GOOD[4:], "T04 answered 500", False)
log(GOOD, "POST instead of GET", False, method="POST")
log([(DA, 200)] * 6, "six requests to one endpoint", False)
print("-- the report (JTL) --")
H = ["timeStamp", "elapsed", "label", "responseCode", "responseMessage", "threadName", "dataType", "success", "failureMessage"]
LAB = ["T01 Admin appointment summary", "T02 Admin payment summary and income", "T03 Admin appointment listing page 2", "T04 Admin income report", "T05 Unauthenticated payment summary", "T06 Patient on the admin appointment list"]
def R(i, code=None, ms=20, ok="true", msg=""): return [1, ms, LAB[i], code or GOOD[i][1], "", "t", "text", ok, msg]
def jtl(rows): w = csv.writer(open(os.path.join(OUT, "results", "run", "results.jtl"), "w", newline="")); w.writerow(H); [w.writerow(r) for r in rows]
def evid(pre=True, post=True, reqs=True, pf=True):
    for n, v in (("pre", pre), ("post", post), ("requests", reqs)): json.dump({"passed": v, "checks": [{"passed": v}]}, open(os.path.join(OUT, "evidence", f"verify-{n}.json"), "w"))
    open(os.path.join(OUT, "evidence", "preflight.txt"), "w").write("PRE-FLIGHT PASSED" if pf else "1 CHECK(S) FAILED")
def summ(name, rows, ok, **kw): jtl(rows); evid(**kw); expect(name, "summarize_six.py", ok)
summ("everything passed", [R(i) for i in range(6)], True)
summ("T04 failed an assertion (status 200)", [R(0), R(1), R(2), R(3, 200, 20, "false", "day 2026-10-10 = 1000/1, expected 3500/2"), R(4), R(5)], False)
summ("T05 answered 200", [R(0), R(1), R(2), R(3), R(4, 200, 20, "false", "code"), R(5)], False)
summ("T06 answered 401 although the assertions passed", [R(0), R(1), R(2), R(3), R(4), R(5, 401)], False)
summ("only five samples", [R(i) for i in range(5)], False)
summ("a seventh sample (a repeated request)", [R(i) for i in range(6)] + [R(0)], False)
summ("two samples for one test case", [R(0), R(0), R(2), R(3), R(4), R(5)], False)
summ("the database changed (post check failed)", [R(i) for i in range(6)], False, post=False)
summ("the server log did not show exactly 6 requests", [R(i) for i in range(6)], False, reqs=False)
summ("the pre-flight did not pass", [R(i) for i in range(6)], False, pf=False)
jtl([R(i) for i in range(6)]); evid(); rc, out = run("summarize_six.py")
shown = all(x in out for x in ("T01", "T06", "6 requests in the JMeter results", "test cases: PASS 6   FAIL 0")) and "median" not in out.replace("average, median or percentile is computed", "") and "p95" not in out
print(("OK    " if shown else "WRONG ") + "the report lists the six test cases with expected status, actual status and time, and makes no statistics claim"); wrong += not shown
shutil.rmtree(T, ignore_errors=True)
print("ALL SIX-SUITE CHECKS BEHAVE AS EXPECTED" if wrong == 0 else f"{wrong} CASE(S) BEHAVED UNEXPECTEDLY"); sys.exit(0 if wrong == 0 else 1)
