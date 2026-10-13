#!/usr/bin/env python3
"""GCN-53 result table: one row per scenario (J01..J06) from <out>/results/run/results.jtl, response-time statistics (average, median, 95th percentile, max; per request type for the repeated
scenario J06), and the run-integrity checks (66 samples in the JTL and 66 requests in the backend's own log, database identical after the run). PASS needs: the expected number of samples, every sample
successful (status, body, authorization behaviour, per-request time cap) and for J06 also the average / p95 thresholds. BLOCKED = no results because the pre-flight failed or JMeter did not run.
Functional response-time smoke test: NO load or concurrency claim."""
import csv, json, math, os, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("GCN53_OUT") or os.path.expanduser("~/carenova/qa-reports/GCN-53/jmeter")
CFG = json.load(open(os.path.join(HERE, "scenarios.json")))["scenarios"]; EV = os.path.join(OUT, "evidence")
def load(n):
    p = os.path.join(EV, n); return json.load(open(p)) if os.path.exists(p) else None
jtl = os.path.join(OUT, "results", "run", "results.jtl"); rows = list(csv.DictReader(open(jtl))) if os.path.exists(jtl) else []
pre, post, reqs = load("verify-pre.json"), load("verify-post.json"), load("verify-requests.json")
pf_ok = os.path.exists(os.path.join(EV, "preflight.txt")) and "PRE-FLIGHT PASSED" in open(os.path.join(EV, "preflight.txt")).read()
def pct(v, p): s = sorted(v); return s[max(0, math.ceil(p / 100 * len(s)) - 1)]
def stats(el): return f"{sum(el)/len(el):.0f}/{statistics.median(el):.0f}/{pct(el, 95)}/{max(el)}"
W = 170
print("=" * W); print("GCN-53 JMETER RESULTS: 6 scenarios, 24 samplers, 66 read-only GET requests, backend :5253, isolated database carenova_appointment_gcn53_qa. Functional / response-time smoke test: NOT a load or concurrency test."); print("=" * W)
print(f"{'ID':5}{'Scenario':36}{'Samplers':9}{'Requests':9}{'Expected':16}{'Actual':14}{'avg/median/p95/max ms':26}{'Result':8}Detail"); print("-" * W)
verdicts = {}; out = []; j06 = {}
for sid, c in CFG.items():
    rs = [r for r in rows if r["label"][:3] == sid]
    exp = str(c["expected_status"])
    if not rs: res, actual, t, detail = ("BLOCKED" if not rows else "NOT RUN"), "-", "-", ("pre-flight failed or JMeter did not run" if not pf_ok else "no sample in the results")
    else:
        el = [int(r["elapsed"]) for r in rs]; codes = {}
        for r in rs: codes[r["responseCode"]] = codes.get(r["responseCode"], 0) + 1
        actual = ", ".join(f"{k} x{v}" for k, v in sorted(codes.items())); t = stats(el)
        failed = [r for r in rs if r["success"] != "true"]
        ok = len(rs) == c["requests"] and not failed
        detail = "all assertions passed" if ok else (f"{len(rs)} samples, expected {c['requests']}; " if len(rs) != c["requests"] else "") + (failed[0]["failureMessage"] or "assertion failed").replace("\n", " ")[:80] + (f" (+{len(failed)-1} more)" if len(failed) > 1 else "")
        if sid == "J06" and len(rs) == c["requests"]:
            mean = sum(el) / len(el); p95 = pct(el, 95); tm = mean <= c["mean_threshold_ms"] and p95 <= c["p95_threshold_ms"] and max(el) <= c["threshold_ms"]
            ok = ok and tm; detail += f"; mean {mean:.0f} ms (limit {c['mean_threshold_ms']}), p95 {p95} ms (limit {c['p95_threshold_ms']}), max {max(el)} ms (limit {c['threshold_ms']}): {'within' if tm else 'EXCEEDED'}"
            for lab in sorted({r["label"] for r in rs}): j06[lab] = [int(r["elapsed"]) for r in rs if r["label"] == lab]
        res = "PASS" if ok else "FAIL"
    verdicts[sid] = res; out.append([sid, c["name"], c["samplers"], c["requests"], exp, actual, t, res, detail])
    print(f"{sid:5}{c['name'][:35]:36}{c['samplers']!s:9}{c['requests']!s:9}{exp[:15]:16}{actual[:13]:14}{t:26}{res:8}{detail}")
print("-" * W)
if j06:
    print("J06 response times by request type (avg/median/p95/max ms):")
    for lab, el in j06.items(): print(f"   {lab:42} n={len(el):3}  {stats(el)}")
    allj = [x for v in j06.values() for x in v]; print(f"   {'all J06 requests':42} n={len(allj):3}  {stats(allj)}")
n = len(rows); labels = sorted({r['label'][:3] for r in rows}); allms = [int(r["elapsed"]) for r in rows]
if rows:
    codes = {}
    for r in rows: codes[r["responseCode"]] = codes.get(r["responseCode"], 0) + 1
    print(f"all {n} requests: status codes {dict(sorted(codes.items()))}; avg/median/p95/max ms = {stats(allms)}; failed samples {sum(r['success'] != 'true' for r in rows)}")
integ = [("JMeter results contain exactly 66 samples (J01 2, J02 5, J03 2, J04 4, J05 8, J06 45)", n == 66 and labels == sorted(CFG)), ("the backend's own request log shows exactly the 66 expected GET requests with the expected statuses", bool(reqs and reqs["passed"])),
         ("the database is IDENTICAL after the run (every table, every row: the suite is read-only)", bool(post and post["passed"])), ("database preconditions held before the run (seeded exactly as the fixtures)", bool(pre and pre["passed"])), ("pre-flight passed (no HTTP request)", pf_ok)]
for name, ok in integ: print(f"  {'PASS' if ok else 'FAIL'}  run integrity: {name}")
c = sum(v == "PASS" for v in verdicts.values()); print(f"\nscenarios: PASS {c}   FAIL {sum(v == 'FAIL' for v in verdicts.values())}   BLOCKED/NOT RUN {sum(v in ('BLOCKED','NOT RUN') for v in verdicts.values())}   (of 6)   total requests: {n}")
print("COVERAGE LIMITS: one thread, sequential requests (J06: 15 iterations of three requests): no concurrency, load or capacity claim. Time limits are sanity thresholds for a local development machine, not service levels.\n  The fixtures are one synthetic data set; the admin user, doctor, fee-request and payment-detail endpoints of other services, the empty-database case and paging beyond 3 pages are not covered here (the backend xUnit tests cover the empty case).")
print("=" * W)
os.makedirs(os.path.join(OUT, "results"), exist_ok=True)
with open(os.path.join(OUT, "results", "GCN-53-JMeter-results.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["id", "scenario", "samplers", "requests", "expected_status", "actual_status", "avg_median_p95_max_ms", "result", "detail"]); w.writerows(out)
sys.exit(0 if c == 6 and all(ok for _, ok in integ) else 1)
