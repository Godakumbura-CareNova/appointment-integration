#!/usr/bin/env python3
"""GCN-47 result table: one row per scenario (JM-01..JM-05, one HTTP request each) from results/run/results.jtl, plus the run-integrity checks (exactly 5 requests in the JTL and in
the backend's own log) and, for JM-05, the read-only database/audit verification. PASS needs: exactly one sample with that label, every assertion passed (status, body, business or
security behaviour), and for JM-05 also the audit/database check. BLOCKED = no results because the pre-flight failed or JMeter did not run. It makes NO coverage claim beyond five requests."""
import csv, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); CFG = json.load(open(os.path.join(HERE, "scenarios.json")))["scenarios"]; EV = os.path.join(HERE, "evidence")
def load(name):
    p = os.path.join(EV, name); return json.load(open(p)) if os.path.exists(p) else None
jtl = os.path.join(HERE, "results", "run", "results.jtl"); rows = list(csv.DictReader(open(jtl))) if os.path.exists(jtl) else []
pre, post, reqs = load("verify-pre.json"), load("verify-post.json"), load("verify-requests.json")
pf_ok = os.path.exists(os.path.join(EV, "preflight.txt")) and "PRE-FLIGHT PASSED" in open(os.path.join(EV, "preflight.txt")).read()
print("=" * 150); print("GCN-47 JMETER RESULTS: 5 scenarios, 5 HTTP requests (one each), backend :5247, isolated database carenova_appointment_gcn47_qa. NOT a load or concurrency test."); print("=" * 150)
print(f"{'ID':7}{'Scenario':36}{'Request':7} {'Role':22}{'Expected':9}{'Actual':8}{'Time':8}{'Result':9}Detail"); print("-" * 150)
verdicts = {}; out = []
for sid, c in CFG.items():
    rs = [r for r in rows if r["label"].startswith(sid + " ")]
    if not rs: res, actual, t, detail = ("BLOCKED" if not rows else "NOT RUN"), "-", "-", ("pre-flight failed or JMeter did not run" if not pf_ok else "no sample in the results")
    else:
        r = rs[0]; actual, t = r["responseCode"], r["elapsed"] + " ms"; ok = len(rs) == 1 and r["success"] == "true" and str(c["expected_status"]) == actual; detail = "all assertions passed" if ok else (f"{len(rs)} samples for one scenario; " if len(rs) != 1 else "") + (r["failureMessage"] or "assertion failed").replace("\n", " ")[:90]
        if sid == "JM-05":
            dbok = bool(post and post["passed"]); ok = ok and dbok; detail = (detail + "; " if ok or r["success"] != "true" else "") + (f"database/audit check {'PASSED' if dbok else 'FAILED or missing'} ({sum(x['passed'] for x in post['checks'])}/{len(post['checks'])})" if post else "database/audit check missing")
        res = "PASS" if ok else "FAIL"
    verdicts[sid] = res; out.append([sid, c["name"], c["method"] + " " + c["path"], c["role"], c["expected_status"], actual, t, res, detail])
    print(f"{sid:7}{c['name'][:35]:36}{c['method']:7} {c['role'][:21]:22}{c['expected_status']!s:9}{actual:8}{t:8}{res:9}{detail}")
print("-" * 150)
n = len(rows); labels = sorted({r['label'][:5] for r in rows})
integ = [("JMeter results contain exactly 5 samples, one per scenario", n == 5 and labels == sorted(CFG)), ("the backend's own request log shows exactly the 5 expected requests (4 GET + 1 PATCH) with statuses 200, 200, 404, 403, 200", bool(reqs and reqs["passed"])),
         ("database preconditions held before the run (seeded, unchanged, no audit row)", bool(pre and pre["passed"])), ("pre-flight passed (no HTTP request)", pf_ok)]
for name, ok in integ: print(f"  {'PASS' if ok else 'FAIL'}  run integrity: {name}")
c = sum(v == "PASS" for v in verdicts.values()); print(f"\nscenarios: PASS {c}   FAIL {sum(v == 'FAIL' for v in verdicts.values())}   BLOCKED/NOT RUN {sum(v in ('BLOCKED','NOT RUN') for v in verdicts.values())}   (of 5)   total HTTP requests: {n}")
print("COVERAGE LIMITS: one request per scenario proves behaviour for ONE input each. JM-03 is a single cross-doctor read (no concurrency, no repeat, no comparison with an unknown id);\n  JM-04 is a single non-Doctor case (Patient role -> 403): no-token 401, invalid/expired tokens, Admin and PharmacyStaff are NOT covered here; the response-time cap is a sanity limit, not performance evidence.")
print("=" * 150)
with open(os.path.join(HERE, "results", "GCN-47-JMeter-results.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["id", "scenario", "request", "role", "expected_status", "actual_status", "time", "result", "detail"]); w.writerows(out)
sys.exit(0 if c == 5 and all(ok for _, ok in integ) else 1)
