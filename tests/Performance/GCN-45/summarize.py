#!/usr/bin/env python3
"""Per-scenario PASS/FAIL table for the GCN-45 JMeter run, from the JTL files. Thresholds and expected sample counts come from scenarios.json (fixed before any run).
   summarize.py --phase seed|readonly|state|concurrent      one phase           summarize.py --all    every phase found (latest run of each)
A scenario is PASS only if: every sample passed (status, body and per-sample time assertions), the sample count equals the expected count
(a skipped sample is a FAIL), and the average and 95th percentile of its product requests are within the threshold. 'NOT RUN' = no samples in the results."""
import csv, collections, json, os, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__)); CFG = json.load(open(os.path.join(HERE, "scenarios.json"))); SC = CFG["scenarios"]; TH = CFG["thresholds"]
args = sys.argv[1:]; phases = ["seed", "readonly", "state", "concurrent"] if "--all" in args else [args[args.index("--phase") + 1]] if "--phase" in args else sys.exit(__doc__)
def key(label):
    first = label.split(" ")[0]
    return first[:5] if first.startswith("JM-") else first
rows = collections.defaultdict(list)
for ph in phases:
    f = os.path.join(HERE, "results", ph, "results.jtl")
    if not os.path.exists(f): continue
    for r in csv.DictReader(open(f)): rows[key(r["label"])].append(r)
present = sum(os.path.exists(os.path.join(HERE, "results", ph, "results.jtl")) for ph in phases)
def pct(t, q): return t[min(len(t) - 1, int(round(q * (len(t) - 1))))]
wanted = [k for k, v in SC.items() if v["phase"] in phases or v["phase"] == "any"]
print("=" * 150); print(f"GCN-45 JMETER RESULTS  phase(s): {', '.join(phases)}  - local backend A:5236 / B:5237, doctor stub:5235, isolated database carenova_appointment_gcn45_qa"); print("=" * 150)
print(f"{'ID':7}{'Scenario':62}{'Result':9}{'N/exp':9}{'Avg':6}{'p95':6}{'Max':6}{'Err%':6} Status codes / reason"); print("-" * 150)
scored_bad = scored = 0; csvrows = []
for k in wanted:
    meta = SC[k]; rs = rows.get(k, []); exp = meta["expected_samples"] * (max(present, 1) if meta["phase"] == "any" else 1); scored_row = k.startswith("JM-")
    if not rs: res, reason, avg, p95, mx, err, codes = "NOT RUN", "no samples", "", "", "", "", ""
    else:
        prod = sorted(int(r["elapsed"]) for r in rs if "[ctl]" not in r["label"] and not r["label"].startswith("SETUP")) or [0]
        failed = [r for r in rs if r["success"] != "true"]; reasons = []
        if failed: reasons.append(f"{len(failed)} failed sample(s): " + " | ".join(f"{r['label'][:50]}: HTTP {r['responseCode']} {r['failureMessage'][:70]}" for r in failed[:3]))
        if len(rs) != exp: reasons.append(f"expected {exp} samples, got {len(rs)}")
        avg, p95, mx = int(statistics.mean(prod)), pct(prod, .95), prod[-1]; t = TH.get(meta["type"], {})
        if t and avg > t["avg_ms"]: reasons.append(f"avg {avg} ms > {t['avg_ms']} ms")
        if t and p95 > t["p95_ms"]: reasons.append(f"p95 {p95} ms > {t['p95_ms']} ms")
        res = "FAIL" if reasons else "PASS"; err = f"{100 * len(failed) / len(rs):.1f}"
        codes = dict(collections.Counter(r["responseCode"] for r in rs)); reason = "; ".join(reasons) or str(codes)
    if scored_row: scored += 1; scored_bad += res != "PASS"
    print(f"{k:7}{meta['name'][:61]:62}{res:9}{(str(len(rs)) + '/' + str(exp)):9}{avg!s:6}{p95!s:6}{mx!s:6}{err!s:6} {reason}")
    csvrows.append([k, meta["name"], res, len(rs), exp, avg, p95, mx, err, reason])
print("-" * 150); print(f"scored scenarios shown: {scored}   PASS {scored - sum(1 for r in csvrows if r[0].startswith('JM-') and r[2] != 'PASS')}   not PASS {scored_bad}   (SETUP/ENV/FX are support steps: a failure there invalidates the phase)"); print("=" * 150)
with open(os.path.join(HERE, "results", "GCN-45-JMeter-results-" + ("all" if "--all" in args else phases[0]) + ".csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["id", "scenario", "result", "samples", "expected", "avg_ms", "p95_ms", "max_ms", "error_pct", "detail"]); w.writerows(csvrows)
