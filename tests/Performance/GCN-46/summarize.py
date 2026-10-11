#!/usr/bin/env python3
"""Per-scenario PASS / FAIL / BLOCKED table for the GCN-46 JMeter run, from the JTL files. Targets come from scenarios.json: PROVISIONAL QA TARGETS (not
official product requirements), fixed before any run and never tuned after results.
   summarize.py --phase functional|load      one phase          summarize.py --all    every phase found
A scenario is PASS only if: no sample failed (status, content/isolation, hard time cap), the sample count equals the expected count (a skipped sample is a FAIL),
and average and p95 are within the target. BLOCKED = the SETUP step failed or is missing (environment not usable). NOT RUN = the phase was not executed.
JM-07 is judged per step; it is reported STOPPED (not passed) if the safety monitor stopped the run."""
import collections, csv, json, os, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__)); CFG = json.load(open(os.path.join(HERE, "scenarios.json"))); SC = CFG["scenarios"]
args = sys.argv[1:]
phases = ["functional", "load"] if "--all" in args else [args[args.index("--phase") + 1]] if "--phase" in args else sys.exit(__doc__)
def label_key(label):
    first = label.split(" ")[0]
    return first if first.startswith("JM-07") else (first[:5] if first.startswith("JM-") else first)
rows = collections.defaultdict(list)
for ph in phases:
    f = os.path.join(HERE, "results", ph, "results.jtl")
    if os.path.exists(f):
        for r in csv.DictReader(open(f)): rows[(ph, label_key(r["label"]))].append(r)
def pct(t, q): return t[min(len(t) - 1, int(round(q * (len(t) - 1))))]
def classify(r):
    m = r["failureMessage"] or ""
    return "status" if "code expected" in m or "Test failed: code" in m else "time" if "slower" in m or "duration" in m.lower() else "content"
def stats(rs):
    t = sorted(int(r["elapsed"]) for r in rs); ok = sum(r["success"] == "true" for r in rs)
    span = max((max(int(r["timeStamp"]) + int(r["elapsed"]) for r in rs) - min(int(r["timeStamp"]) for r in rs)) / 1000, 0.001)
    bad = [r for r in rs if r["success"] != "true"]; kinds = collections.Counter(classify(r) for r in bad)
    return dict(n=len(rs), ok=ok, fail=len(rs) - ok, avg=int(statistics.mean(t)), p95=pct(t, .95), mx=t[-1], thr=len(rs) / span, err=100 * (len(rs) - ok) / len(rs), kinds=kinds, bad=bad,
                codes=dict(collections.Counter(r["responseCode"] for r in rs)))
def setup_state(ph):
    s = rows.get((ph, "SETUP"), [])
    return "missing" if not s else ("ok" if all(r["success"] == "true" for r in s) else "failed")
out = []; shown = []
H = f"{'ID':8}{'Scenario':50}{'Result':9}{'Total':7}{'OK':7}{'Fail':6}{'Avg':6}{'p95':6}{'Max':6}{'Thr/s':7}{'Err%':6}{'status/content/time failures'}"
print("=" * 170); print("GCN-46 JMETER RESULTS  (targets are provisional QA targets, not official product requirements)  backend :5246, isolated database carenova_appointment_gcn46_qa"); print("=" * 170)
print(H); print("-" * 170)
def line(i, name, res, s, extra=""):
    if s: print(f"{i:8}{name[:49]:50}{res:9}{s['n']:<7}{s['ok']:<7}{s['fail']:<6}{s['avg']:<6}{s['p95']:<6}{s['mx']:<6}{s['thr']:<7.1f}{s['err']:<6.1f}{s['kinds'].get('status', 0)}/{s['kinds'].get('content', 0)}/{s['kinds'].get('time', 0)}  {extra}")
    else: print(f"{i:8}{name[:49]:50}{res:9}{'-':7}{'-':7}{'-':6}{'-':6}{'-':6}{'-':6}{'-':7}{'-':6}  {extra}")
    out.append([i, name, res, s["n"] if s else "", s["ok"] if s else "", s["fail"] if s else "", s["avg"] if s else "", s["p95"] if s else "", s["mx"] if s else "", round(s["thr"], 1) if s else "", round(s["err"], 1) if s else "", extra])
verdicts = {}
for sid, meta in SC.items():
    ph = meta["phase"]; ph_list = phases if ph == "any" else [ph]
    if not any(p in phases for p in ph_list): continue
    ran = [p for p in ph_list if p in phases and os.path.exists(os.path.join(HERE, "results", p, "results.jtl"))]
    if sid in ("SETUP", "ENV"):
        rs = [r for p in ran for r in rows.get((p, sid), [])]
        if rs: s = stats(rs); line(sid, meta["name"], "ok" if not s["fail"] else "FAILED", s, "support step")
        continue
    if not ran: line(sid, meta["name"], "NOT RUN", None, "phase not executed"); verdicts[sid] = "NOT RUN"; continue
    if setup_state(ran[0]) != "ok": line(sid, meta["name"], "BLOCKED", None, f"SETUP {setup_state(ran[0])}: environment not usable"); verdicts[sid] = "BLOCKED"; continue
    if sid != "JM-07":
        rs = rows.get((ran[0], sid), [])
        if not rs: line(sid, meta["name"], "NOT RUN", None, "no samples"); verdicts[sid] = "NOT RUN"; continue
        s = stats(rs); why = []
        if s["fail"]: why.append(f"{s['fail']} failed sample(s): " + " | ".join(f"{r['label'][8:60]} [{r['responseCode']}] {(r['failureMessage'] or '')[:80]}" for r in s["bad"][:2]))
        if s["n"] != meta["expected"]: why.append(f"expected {meta['expected']} samples, got {s['n']}")
        if s["avg"] > meta["avg_ms"]: why.append(f"avg {s['avg']} ms > target {meta['avg_ms']} ms")
        if s["p95"] > meta["p95_ms"]: why.append(f"p95 {s['p95']} ms > target {meta['p95_ms']} ms")
        res = "FAIL" if why else "PASS"; verdicts[sid] = res; line(sid, meta["name"], res, s, "; ".join(why) or str(s["codes"]))
        continue
    # JM-07: per step
    stopf = os.path.join(HERE, "results", "load", "monitor-stop.txt"); stopped = os.path.exists(stopf); why = []; base = None; steps = {}
    for step, t in meta["steps"].items():
        rs = rows.get(("load", step), [])
        if not rs: why.append(f"{step}: no samples"); continue
        s = stats(rs); steps[step] = s; local = []
        if s["n"] < t["min_samples"]: local.append(f"only {s['n']} samples (< {t['min_samples']})")
        if s["kinds"].get("content"): local.append(f"{s['kinds']['content']} CONTENT failures (zero tolerance)")
        if s["err"] > t["max_error_pct"]: local.append(f"error {s['err']:.2f}% > {t['max_error_pct']}%")
        if "avg_ms" in t and s["avg"] > t["avg_ms"]: local.append(f"avg {s['avg']} > {t['avg_ms']} ms")
        if "p95_ms" in t and s["p95"] > t["p95_ms"]: local.append(f"p95 {s['p95']} > {t['p95_ms']} ms")
        if step == "JM-07a": base = s
        if step == "JM-07d" and base is not None:
            lim = max(500, 1.5 * base["p95"])
            if s["p95"] > lim: local.append(f"recovery p95 {s['p95']} > max(500, 1.5 x baseline {base['p95']}) = {lim:.0f} ms")
        elif step == "JM-07d": local.append("no baseline to compare")
        why += [f"{step}: {x}" for x in local]
    res = "STOPPED" if stopped else ("FAIL" if why or len(steps) < 4 else "PASS"); verdicts[sid] = res
    allrs = [r for st in ("JM-07a", "JM-07b", "JM-07c", "JM-07d") for r in rows.get(("load", st), [])]
    line(sid, meta["name"], res, stats(allrs) if allrs else None, ("monitor stopped the run: " + open(stopf).read().strip()[:80] if stopped else "; ".join(why) or "all four steps within target"))
    for step, s in steps.items(): line("  " + step[-1], "   " + meta["steps"][step]["name"], "", s, "")
print("-" * 170)
c = collections.Counter(v for k, v in verdicts.items()); print("scenarios: " + "   ".join(f"{k} {v}" for k, v in sorted(c.items())) + f"   (of {len(verdicts)})"); print("=" * 170)
os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
with open(os.path.join(HERE, "results", "GCN-46-JMeter-results-" + ("all" if "--all" in args else phases[0]) + ".csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["id", "scenario", "result", "total", "ok", "failed", "avg_ms", "p95_ms", "max_ms", "throughput_per_s", "error_pct", "detail"]); w.writerows(out)
