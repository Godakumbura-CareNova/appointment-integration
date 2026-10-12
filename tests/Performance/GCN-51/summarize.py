#!/usr/bin/env python3
"""GCN-51 result table: one row per scenario (J01..J09) from results/run/results.jtl, plus run-integrity checks (38 samples in the JTL and 38 requests in the backend's own log, database unchanged)
and the J09 response-time statistics against the documented thresholds. PASS needs: the expected number of samples, every sample successful (status, body, business/security behaviour, per-request time cap),
and the expected status. BLOCKED = no results because the pre-flight failed or JMeter did not run. Functional / response-time / repeated-request smoke test: NO load or concurrency claim."""
import csv, json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); CFG = json.load(open(os.path.join(HERE, "scenarios.json")))["scenarios"]; EV = os.path.join(HERE, "evidence")
def load(n):
    p = os.path.join(EV, n); return json.load(open(p)) if os.path.exists(p) else None
jtl = os.path.join(HERE, "results", "run", "results.jtl"); rows = list(csv.DictReader(open(jtl))) if os.path.exists(jtl) else []
pre, post, reqs = load("verify-pre.json"), load("verify-post.json"), load("verify-requests.json")
pf_ok = os.path.exists(os.path.join(EV, "preflight.txt")) and "PRE-FLIGHT PASSED" in open(os.path.join(EV, "preflight.txt")).read()
W = 160
print("=" * W); print("GCN-51 JMETER RESULTS: 9 scenarios, 9 samplers, 38 read-only GET requests, backend :5251, isolated database carenova_appointment_gcn51_qa. Functional / response-time / repeated-request smoke test: NOT a load or concurrency test."); print("=" * W)
print(f"{'ID':5}{'Scenario':46}{'Requests':9}{'Expected':9}{'Actual':8}{'Time ms (min/mean/p95/max)':30}{'Result':9}Detail"); print("-" * W)
def pct(v, p): s = sorted(v); return s[max(0, math.ceil(p / 100 * len(s)) - 1)]
verdicts = {}; out = []; j09 = None
for sid, c in CFG.items():
    rs = [r for r in rows if r["label"].split()[0] == sid]
    if not rs: res, actual, t, detail = ("BLOCKED" if not rows else "NOT RUN"), "-", "-", ("pre-flight failed or JMeter did not run" if not pf_ok else "no sample in the results")
    else:
        el = [int(r["elapsed"]) for r in rs]; codes = sorted({r["responseCode"] for r in rs}); actual = "/".join(codes)
        t = f"{min(el)}/{sum(el)//len(el)}/{pct(el, 95)}/{max(el)}"
        failed = [r for r in rs if r["success"] != "true" or r["responseCode"] != str(c["expected_status"])]
        ok = len(rs) == c["requests"] and not failed
        detail = "all assertions passed" if ok else (f"{len(rs)} samples, expected {c['requests']}; " if len(rs) != c["requests"] else "") + (failed[0]["failureMessage"] or "assertion failed").replace("\n", " ")[:80] + (f" (+{len(failed)-1} more)" if len(failed) > 1 else "")
        if sid == "J09" and len(rs) == c["requests"]:
            mean = sum(el) / len(el); p95 = pct(el, 95); j09 = (mean, p95, max(el))
            tm = mean <= c["mean_threshold_ms"] and p95 <= c["p95_threshold_ms"] and max(el) <= c["threshold_ms"]
            ok = ok and tm; detail = (detail + "; " if ok or not tm else detail + "; ") + f"mean {mean:.0f} ms (limit {c['mean_threshold_ms']}), p95 {p95} ms (limit {c['p95_threshold_ms']}), max {max(el)} ms (limit {c['threshold_ms']}): {'within' if tm else 'EXCEEDED'}"
        res = "PASS" if ok else "FAIL"
    verdicts[sid] = res; out.append([sid, c["name"], c["requests"], c["expected_status"], actual, t, res, detail])
    print(f"{sid:5}{c['name'][:45]:46}{c['requests']!s:9}{c['expected_status']!s:9}{actual[:7]:8}{t:30}{res:9}{detail}")
print("-" * W)
n = len(rows); labels = sorted({r['label'].split()[0] for r in rows})
integ = [("JMeter results contain exactly 38 samples (J01-J08: 8 samples, J09: 30)", n == 38 and labels == sorted(CFG)), ("the backend's own request log shows exactly the 38 expected GET requests with the expected statuses", bool(reqs and reqs["passed"])),
         ("the database is IDENTICAL after the run (every table, every row: the suite is read-only)", bool(post and post["passed"])), ("database preconditions held before the run (seeded exactly as the fixtures)", bool(pre and pre["passed"])), ("pre-flight passed (no HTTP request)", pf_ok)]
for name, ok in integ: print(f"  {'PASS' if ok else 'FAIL'}  run integrity: {name}")
c = sum(v == "PASS" for v in verdicts.values()); print(f"\nscenarios: PASS {c}   FAIL {sum(v == 'FAIL' for v in verdicts.values())}   BLOCKED/NOT RUN {sum(v in ('BLOCKED','NOT RUN') for v in verdicts.values())}   (of 9)   total requests: {n}")
print("COVERAGE LIMITS: one thread, sequential requests (J09: one sampler looped 30 times on the staff payments dashboard only): no concurrency, load or capacity claim. Time limits are sanity thresholds for a local development machine, not service levels. J06 covers the unauthenticated staff dashboard only. The fixtures cover ONE patient's and ONE staff view;\n  the pharmacy-order and doctor-payment dashboard endpoints (medicine orders, medicine payments) belong to other services and are NOT covered here; there is no doctor dashboard endpoint in this backend (J05 uses GET /api/doctor/appointments);\n  Admin, 'User' role alias, expired/invalid tokens and the reconciliation exclusion of income are not covered by this plan (the backend xUnit tests cover them).")
print("=" * W)
with open(os.path.join(HERE, "results", "GCN-51-JMeter-results.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["id", "scenario", "requests", "expected_status", "actual_status", "time_ms_min_mean_p95_max", "result", "detail"]); w.writerows(out)
sys.exit(0 if c == 9 and all(ok for _, ok in integ) else 1)
