#!/usr/bin/env python3
"""Offline self-test of gcn53_verify.py and summarize.py with a FAKE mysql client and synthetic JTL files: no database, no server, no network. Checks that the verifier and the summary ACCEPT correct
states and REJECT every deliberately corrupted one. Exit 1 if any case behaves differently from what is expected."""
import copy, csv, datetime as dt, json, os, shutil, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); T = tempfile.mkdtemp(prefix="gcn53-verifier-test-"); OUT = os.path.join(T, "out")
FAKE = '''#!/usr/bin/env python3
import json, os, sys
a = sys.argv; sql = a[a.index("-e") + 1]; st = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "state.json")))
def emit(rows):
    for r in rows: print("\\t".join(str(x) for x in r))
if sql.startswith("SELECT (SELECT COUNT(*) FROM Appointments)"): emit([st["counts"]])
elif "FROM AppointmentPayments ORDER" in sql: emit(st["payments"])
elif "FROM AppointmentReceipts ORDER" in sql: emit(st["receipts"])
elif "FROM Appointments ORDER" in sql: emit(st["appointments"])
else: sys.exit("fake mysql: unexpected query " + sql[:60])
'''
os.makedirs(os.path.join(T, "bin")); open(os.path.join(T, "bin", "mysql"), "w").write(FAKE); os.chmod(os.path.join(T, "bin", "mysql"), 0o755)
for d in ("fixtures", "evidence", "logs", "results"): os.makedirs(os.path.join(OUT, d))
for f in ("gcn53_verify.py", "summarize.py", "scenarios.json"): shutil.copy(os.path.join(HERE, f), T)
subprocess.run([sys.executable, os.path.join(HERE, "gen_gcn53_fixtures.py"), "--out-dir", os.path.join(OUT, "fixtures")], check=True, capture_output=True)
FX = json.load(open(os.path.join(OUT, "fixtures", "fixtures.json"))); ENV = {**os.environ, "PATH": os.path.join(T, "bin") + os.pathsep + os.environ["PATH"], "GCN53_DB_PASSWORD": "offline-dummy", "GCN53_OUT": OUT}
FMT = "%Y-%m-%dT%H:%M:%SZ"; f6 = lambda s: dt.datetime.strptime(s, FMT).strftime("%Y-%m-%d %H:%M:%S.000000"); DOC = "53d10000-0000-4000-8000-000000000001"
def seeded():
    ap = [[a["id"], a["appointmentReference"], a["patientId"], DOC, a["status"], f6(a["startUtc"]), f6(a["endUtc"]), "NULL"] for a in FX["appointments"]]
    pay = [[p["id"], p["appointmentId"], p["patientId"], p["method"], p["status"], p["amount"], f6(p["confirmedAtUtc"]) if p["confirmedAtUtc"] else "NULL", f6(p["updatedAtUtc"])] for p in FX["payments"]["payments"]]
    rec = [[53007, 53007, 53007, FX["appointments"][6]["patientId"], "PendingVerification", f6(FX["generatedAtUtc"])], [53008, 53008, 53008, FX["appointments"][7]["patientId"], "Rejected", f6(FX["generatedAtUtc"])]]
    return {"appointments": ap, "payments": pay, "receipts": rec, "counts": [len(ap), len(pay), len(rec), 0, 0, 0, 0, 0]}
def run(script, state, mode):
    json.dump(state, open(os.path.join(T, "state.json"), "w"))
    r = subprocess.run([sys.executable, os.path.join(T, script)] + ([mode] if script.startswith("gcn53") else []), capture_output=True, text=True, env=ENV, cwd=T); return r.returncode, r.stdout
wrong = 0
def expect(name, state, mode, ok, script="gcn53_verify.py"):
    global wrong; rc, out = run(script, state, mode); good = (rc == 0) == ok; wrong += not good
    fails = [l.strip()[6:88] for l in out.splitlines() if l.strip().startswith("FAIL")][:1]
    print(("OK    " if good else "WRONG ") + f"{mode:8} {name:80}" + (" -> rejected: " + fails[0] if rc and fails else (" -> accepted" if rc == 0 else " -> rejected")))
S = seeded()
def mut(fn):
    s = copy.deepcopy(S); fn(s); return s
print("-- pre (before the run) --")
expect("the seeded state", S, "pre", True)
expect("an appointment status differs", mut(lambda s: s["appointments"][0].__setitem__(4, "Cancelled")), "pre", False)
expect("an appointment was already updated", mut(lambda s: s["appointments"][0].__setitem__(7, "2026-10-12 00:00:00.000000")), "pre", False)
expect("a payment amount differs", mut(lambda s: s["payments"][1].__setitem__(5, "1.00")), "pre", False)
expect("a payment confirmation date differs", mut(lambda s: s["payments"][0].__setitem__(6, "NULL")), "pre", False)
expect("the pending receipt is Verified", mut(lambda s: s["receipts"][0].__setitem__(4, "Verified")), "pre", False)
expect("a cancellation row exists", mut(lambda s: s["counts"].__setitem__(5, 1)), "pre", False)
expect("an appointment is missing", mut(lambda s: (s["appointments"].pop(), s["counts"].__setitem__(0, len(s["appointments"])))), "pre", False)
expect("a non-synthetic patient id", mut(lambda s: s["appointments"][0].__setitem__(2, "11111111-1111-1111-1111-111111111111")), "pre", False)
run("gcn53_verify.py", S, "pre")        # saves evidence/verify-pre.json for the post cases
print("-- post (after the run: read-only proof) --")
expect("every table identical", S, "post", True)
expect("a payment status changed", mut(lambda s: s["payments"][0].__setitem__(4, "Failed")), "post", False)
expect("an appointment status changed", mut(lambda s: s["appointments"][3].__setitem__(4, "Cancelled")), "post", False)
expect("an appointment UpdatedAtUtc was set", mut(lambda s: s["appointments"][3].__setitem__(7, "2026-10-12 01:00:00.000000")), "post", False)
expect("a receipt changed", mut(lambda s: s["receipts"][0].__setitem__(4, "Verified")), "post", False)
expect("a row was added", mut(lambda s: (s["appointments"].append([9, "x", "53a", "53d", "Booked", "2031-01-01 00:00:00.000000", "2031-01-01 00:30:00.000000", "NULL"]), s["counts"].__setitem__(0, len(s["appointments"])))), "post", False)
expect("a row was deleted", mut(lambda s: (s["payments"].pop(), s["counts"].__setitem__(1, len(s["payments"])))), "post", False)
expect("a refund row appeared", mut(lambda s: s["counts"].__setitem__(6, 1)), "post", False)
print("-- requests (the backend's own log) --")
base = 8; open(os.path.join(OUT, "evidence", "log-baseline.txt"), "w").write(str(base)); pre_lines = ["info: startup"] * base
DA, DP, AL, RP = "/api/admin/dashboard/appointments", "/api/admin/dashboard/appointment-payments", "/api/admin/appointments", "/api/admin/reports/appointment-income"
def lines(m, p, st): return [f"      Request starting HTTP/1.1 {m} http://localhost:5253{p} - - -", f"      Request finished HTTP/1.1 {m} http://localhost:5253{p} - {st} - application/json;+charset=utf-8 5.0ms"]
GOOD = ([(DA, 200), (DP, 200)] + [(AL, 200)] * 4 + [(AL, 400)] + [(RP, 200), (RP, 400)] + [(DA, 401), (DP, 401), (AL, 401), (RP, 401)]
        + [(DA, 403), (DP, 403), (AL, 403), (RP, 403), (DA, 403), (AL, 403), (DP, 403), (RP, 403)] + [(DA, 200), (DP, 200), (AL, 200)] * 15)
def log(reqs, name, ok, method="GET"):
    open(os.path.join(OUT, "logs", "backend.log"), "w").write("\n".join(pre_lines + sum((lines(method, p, st) for p, st in reqs), [])) + "\n"); expect(name, S, "requests", ok)
log(GOOD, "exactly the 66 expected requests", True)
log(GOOD + [("/health", 200)], "a 67th request (health check)", False)
log(GOOD[:-1], "only 65 requests", False)
log(GOOD + [GOOD[-1]], "one repeated request (retry)", False)
log([GOOD[0], GOOD[2], GOOD[1]] + GOOD[3:], "payment summary and list swapped (order matters)", False)
log(GOOD[:8] + [(RP, 200)] + GOOD[9:], "J03b answered 200 instead of 400", False)
log(GOOD[:9] + [(DA, 200)] + GOOD[10:], "J04a answered 200 instead of 401", False)
log(GOOD[:15] + [(DA, 401)] + GOOD[16:], "J05a answered 401 instead of 403", False)
log(GOOD, "a POST instead of a GET", False, method="POST")
log(GOOD[:30] + [(AL, 500)] + GOOD[31:], "one J06 request answered 500", False)
print("-- summary (JTL) --")
H = ["timeStamp", "elapsed", "label", "responseCode", "responseMessage", "threadName", "dataType", "success", "failureMessage"]
LABELS = ["J01a x", "J01b x"] + [f"J02{c} x" for c in "abcde"] + ["J03a x", "J03b x"] + [f"J04{c} x" for c in "abcd"] + [f"J05{c} x" for c in "abcdefgh"]
def jtl(rows):
    os.makedirs(os.path.join(OUT, "results", "run"), exist_ok=True); w = csv.writer(open(os.path.join(OUT, "results", "run", "results.jtl"), "w", newline="")); w.writerow(H); [w.writerow(r) for r in rows]
def R(label, code, ms=20, ok="true", msg=""): return [1, ms, label, code, "", "t", "text", ok, msg]
def good(ms6=100):
    rows = [R(l, c, 20) for l, (_, c) in zip(LABELS, GOOD[:21])]
    return rows + [R(["J06a x", "J06b x", "J06c x"][i % 3], 200, ms6) for i in range(45)]
def evid(pre=True, post=True, reqs=True, pf=True):
    for n, v in (("pre", pre), ("post", post), ("requests", reqs)): json.dump({"passed": v, "checks": [{"passed": v}]}, open(os.path.join(OUT, "evidence", f"verify-{n}.json"), "w"))
    open(os.path.join(OUT, "evidence", "preflight.txt"), "w").write("PRE-FLIGHT PASSED" if pf else "1 CHECK(S) FAILED")
def summ(name, rows, ok, **kw): jtl(rows); evid(**kw); expect(name, S, "-", ok, script="summarize.py")
summ("everything passed", good(), True)
summ("J06 mean above its limit (every request within the per-request cap)", good(ms6=450), False)
summ("J06 one request above the per-request cap", good()[:30] + [R("J06a x", 200, 1600)] + good()[31:], False)
summ("J06 only 44 samples", good()[:-1], False)
summ("J03a failed an assertion (status 200)", good()[:7] + [R("J03a x", 200, 20, "false", "day 2026-10-10 = 1000/1, expected 3500/2")] + good()[8:], False)
summ("J04a answered 200", good()[:11] + [R("J04a x", 200, 20, "false", "code")] + good()[12:], False)
summ("the database changed (post check failed)", good(), False, post=False)
summ("the server log did not show exactly 66 requests", good(), False, reqs=False)
summ("a 67th sample in the JTL", good() + [R("J01a x", 200)], False)
rc, out = run("summarize.py", S, "-"); jtl(good()); evid(); rc, out = run("summarize.py", S, "-")
stats_ok = "J06 response times by request type" in out and "all 66 requests" in out and "avg/median/p95/max" in out
print(("OK    " if stats_ok else "WRONG ") + "the summary reports average, median and 95th percentile per request type and overall"); wrong += not stats_ok
shutil.rmtree(T, ignore_errors=True)
print("ALL VERIFIER AND SUMMARY CASES BEHAVE AS EXPECTED" if wrong == 0 else f"{wrong} CASE(S) BEHAVED UNEXPECTEDLY"); sys.exit(0 if wrong == 0 else 1)
