#!/usr/bin/env python3
"""GCN-53 six-request suite report: one row per test case (T01..T06, one HTTP GET each) from <out>/results/run/results.jtl with expected status, actual status, response time and PASS/FAIL,
plus the run-integrity checks (6 samples, 6 requests in the backend's own log, database identical after the run). PASS needs: exactly one sample for the test case, success=true (status, body,
authorization behaviour and the 3000 ms sanity cap all asserted by the plan) and the expected status. BLOCKED = no results because the pre-flight failed or JMeter did not run.
One sample per test case: no average, median or percentile is computed or claimed. Functional smoke test only."""
import csv, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.environ.get("GCN53_OUT") or os.path.expanduser("~/carenova/qa-reports/GCN-53/jmeter-six")
CFG = json.load(open(os.path.join(HERE, "scenarios.json")))["scenarios"]; EV = os.path.join(OUT, "evidence")
def load(n):
    p = os.path.join(EV, n); return json.load(open(p)) if os.path.exists(p) else None
jtl = os.path.join(OUT, "results", "run", "results.jtl"); rows = list(csv.DictReader(open(jtl))) if os.path.exists(jtl) else []
pre, post, reqs = load("verify-pre.json"), load("verify-post.json"), load("verify-requests.json")
pf_ok = os.path.exists(os.path.join(EV, "preflight.txt")) and "PRE-FLIGHT PASSED" in open(os.path.join(EV, "preflight.txt")).read()
W = 160
print("=" * W); print("GCN-53 SIX-REQUEST JMETER REPORT: 6 test cases, 6 HTTP GET requests (one each), backend :5253, isolated database carenova_appointment_gcn53_qa. Functional smoke test: NOT a load, concurrency or statistics test."); print("=" * W)
print(f"{'ID':5}{'Test case':44}{'Request':50}{'Expected':9}{'Actual':8}{'Time':9}{'Result':8}Detail"); print("-" * W)
verdicts = {}; out = []
for sid, c in CFG.items():
    rs = [r for r in rows if r["label"][:3] == sid]
    if not rs: res, actual, t, detail = ("BLOCKED" if not rows else "NOT RUN"), "-", "-", ("pre-flight failed or JMeter did not run" if not pf_ok else "no sample in the results")
    else:
        r = rs[0]; actual, t = r["responseCode"], r["elapsed"] + " ms"; ok = len(rs) == 1 and r["success"] == "true" and actual == str(c["expected_status"])
        detail = "all assertions passed" if ok else (f"{len(rs)} samples for one test case; " if len(rs) != 1 else "") + (r["failureMessage"] or "assertion failed").replace("\n", " ")[:90]
        res = "PASS" if ok else "FAIL"
    verdicts[sid] = res; req = f"{c['method']} {c['path']} ({c['role']})"; out.append([sid, c["name"], req, c["expected_status"], actual, t, res, detail])
    print(f"{sid:5}{c['name'][:43]:44}{req[:49]:50}{c['expected_status']!s:9}{actual:8}{t:9}{res:8}{detail}")
print("-" * W)
n = len(rows); labels = sorted({r['label'][:3] for r in rows}); codes = {}
for r in rows: codes[r["responseCode"]] = codes.get(r["responseCode"], 0) + 1
if rows: print(f"{n} requests in the JMeter results; status codes {dict(sorted(codes.items()))}; failed samples {sum(r['success'] != 'true' for r in rows)}")
integ = [("JMeter results contain exactly 6 samples, one per test case", n == 6 and labels == sorted(CFG)), ("the backend's own request log shows exactly the 6 expected GET requests with statuses 200, 200, 200, 200, 401, 403", bool(reqs and reqs["passed"])),
         ("the database is IDENTICAL after the run (every table, every row: the suite is read-only)", bool(post and post["passed"])), ("database preconditions held before the run (seeded exactly as the fixtures)", bool(pre and pre["passed"])), ("pre-flight passed (no HTTP request)", pf_ok)]
for name, ok in integ: print(f"  {'PASS' if ok else 'FAIL'}  run integrity: {name}")
c = sum(v == "PASS" for v in verdicts.values()); print(f"\ntest cases: PASS {c}   FAIL {sum(v == 'FAIL' for v in verdicts.values())}   BLOCKED/NOT RUN {sum(v in ('BLOCKED','NOT RUN') for v in verdicts.values())}   (of 6)   total requests: {n}")
print("COVERAGE LIMITS: six requests, one per behavior, one thread: no concurrency, load, stability or response-time-statistics claim (the single response times above are one sample each). Not covered here: search, the 400 cases, the other non-admin roles, the 401 on the list and report endpoints, repeated requests; the 66-request suite covers those.")
print("=" * W)
os.makedirs(os.path.join(OUT, "results"), exist_ok=True)
with open(os.path.join(OUT, "results", "GCN-53-six-results.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["id", "test_case", "request", "expected_status", "actual_status", "response_time", "result", "detail"]); w.writerows(out)
sys.exit(0 if c == 6 and all(ok for _, ok in integ) else 1)
