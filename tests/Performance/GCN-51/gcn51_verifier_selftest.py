#!/usr/bin/env python3
"""Offline self-test of gcn51_verify.py and summarize.py with a FAKE mysql client and synthetic JTL files: no database, no server, no network. Checks that the verifier and the summary ACCEPT correct
states and REJECT every deliberately corrupted one. Exit 1 if any case behaves differently from what is expected."""
import copy, csv, datetime as dt, json, os, shutil, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); T = tempfile.mkdtemp(prefix="gcn51-verifier-test-")
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
for d in ("fixtures", "evidence", "logs", "results"): os.makedirs(os.path.join(T, d))
for f in ("gcn51_verify.py", "summarize.py", "scenarios.json"): shutil.copy(os.path.join(HERE, f), T)
subprocess.run([sys.executable, os.path.join(HERE, "gen_gcn51_fixtures.py"), "--out-dir", os.path.join(T, "fixtures")], check=True, capture_output=True)
FX = json.load(open(os.path.join(T, "fixtures", "fixtures.json"))); ENV = {**os.environ, "PATH": os.path.join(T, "bin") + os.pathsep + os.environ["PATH"], "GCN51_DB_PASSWORD": "offline-dummy"}
FMT = "%Y-%m-%dT%H:%M:%SZ"; f6 = lambda s: dt.datetime.strptime(s, FMT).strftime("%Y-%m-%d %H:%M:%S.000000")
def seeded():
    ap = [[a["id"], a["appointmentReference"], a["patientId"], a["doctorId"], a["status"], f6(a["startUtc"]), f6(a["endUtc"]), "NULL"] for a in FX["appointments"]]
    pay = [[p["id"], p["appointmentId"], p["patientId"], p["method"], p["status"], p["amount"], f6(p["confirmedAtUtc"]) if p["confirmedAtUtc"] else "NULL", f6(p["updatedAtUtc"])] for p in FX["staff"]["payments"]]
    ids = {a["id"]: a for a in FX["appointments"]}
    rec = [[r, r, r, ids[r]["patientId"], "Rejected" if r == 51109 else "PendingVerification", f6(FX["generatedAtUtc"])] for r in (51003, 51101, 51105, 51106, 51107, 51108, 51109)]
    return {"appointments": ap, "payments": pay, "receipts": rec, "counts": [len(ap), len(pay), len(rec), 0, 0, 0, 0, 0]}
def run(script, state, mode):
    json.dump(state, open(os.path.join(T, "state.json"), "w"))
    r = subprocess.run([sys.executable, os.path.join(T, script), mode] if script.startswith("gcn51") else [sys.executable, os.path.join(T, script)], capture_output=True, text=True, env=ENV, cwd=T); return r.returncode, r.stdout
wrong = 0
def expect(name, state, mode, ok, script="gcn51_verify.py"):
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
expect("a payment confirmation date differs", mut(lambda s: s["payments"][1].__setitem__(6, "NULL")), "pre", False)
expect("a pending receipt is Verified", mut(lambda s: s["receipts"][0].__setitem__(4, "Verified")), "pre", False)
expect("a cancellation row exists", mut(lambda s: s["counts"].__setitem__(5, 1)), "pre", False)
expect("a refund row exists", mut(lambda s: s["counts"].__setitem__(6, 1)), "pre", False)
expect("an appointment is missing", mut(lambda s: (s["appointments"].pop(), s["counts"].__setitem__(0, len(s["appointments"])))), "pre", False)
expect("a non-synthetic patient id", mut(lambda s: s["appointments"][0].__setitem__(2, "11111111-1111-1111-1111-111111111111")), "pre", False)
run("gcn51_verify.py", S, "pre")        # saves evidence/verify-pre.json for the post cases
print("-- post (after the run: read-only proof) --")
expect("every table identical", S, "post", True)
expect("a payment status changed", mut(lambda s: s["payments"][0].__setitem__(4, "Successful")), "post", False)
expect("an appointment status changed", mut(lambda s: s["appointments"][3].__setitem__(4, "Cancelled")), "post", False)
expect("an appointment UpdatedAtUtc was set", mut(lambda s: s["appointments"][3].__setitem__(7, "2026-10-12 01:00:00.000000")), "post", False)
expect("a receipt changed", mut(lambda s: s["receipts"][0].__setitem__(4, "Verified")), "post", False)
expect("a row was added", mut(lambda s: (s["appointments"].append([9, "x", "51a", "51d", "Booked", "2031-01-01 00:00:00.000000", "2031-01-01 00:30:00.000000", "NULL"]), s["counts"].__setitem__(0, len(s["appointments"])))), "post", False)
expect("a row was deleted", mut(lambda s: (s["payments"].pop(), s["counts"].__setitem__(1, len(s["payments"])))), "post", False)
expect("a cancellation row appeared", mut(lambda s: s["counts"].__setitem__(5, 1)), "post", False)
print("-- requests (the backend's own log) --")
base = 8; open(os.path.join(T, "evidence", "log-baseline.txt"), "w").write(str(base)); pre_lines = ["info: startup"] * base
PD, SD, DD = "/api/patient/dashboard/appointments", "/api/staff/dashboard/appointment-payments", "/api/doctor/appointments"
def lines(m, p, st): return [f"      Request starting HTTP/1.1 {m} http://localhost:5251{p} - - -", f"      Request finished HTTP/1.1 {m} http://localhost:5251{p} - {st} - application/json;+charset=utf-8 5.0ms"]
GOOD = [("GET", PD, 200), ("GET", PD, 200), ("GET", SD, 200), ("GET", SD, 200), ("GET", DD, 200), ("GET", SD, 401), ("GET", SD, 403), ("GET", PD, 403)] + [("GET", SD, 200)] * 30
def log(reqs, name, ok):
    open(os.path.join(T, "logs", "backend.log"), "w").write("\n".join(pre_lines + sum((lines(*r) for r in reqs), [])) + "\n"); expect(name, S, "requests", ok)
log(GOOD, "exactly the 38 expected requests", True)
log(GOOD + [("GET", "/health", 200)], "a 39th request (health check)", False)
log(GOOD[:-1], "only 37 requests", False)
log(GOOD + [GOOD[-1]], "one repeated request (retry)", False)
log(GOOD[:3] + [GOOD[4], GOOD[3]] + GOOD[5:], "J04 and J05 requests swapped (order matters)", False)
log(GOOD[:5] + [("GET", SD, 200)] + GOOD[6:], "J06 answered 200 instead of 401", False)
log(GOOD[:6] + [("GET", SD, 401)] + GOOD[7:], "J07 answered 401 instead of 403", False)
log(GOOD[:7] + [("POST", PD, 403)] + GOOD[8:], "a POST instead of a GET", False)
log(GOOD[:20] + [("GET", SD, 500)] + GOOD[21:], "one J09 request answered 500", False)
print("-- summary (JTL) --")
H = ["timeStamp", "elapsed", "label", "responseCode", "responseMessage", "threadName", "dataType", "success", "failureMessage"]
LAB = {"J01": "J01 Patient dashboard summary", "J02": "J02 Patient dashboard counts and preview", "J03": "J03 Pharmacy staff dashboard summary", "J04": "J04 Pharmacy staff payments and income", "J05": "J05 Doctor appointments data",
       "J06": "J06 Unauthenticated staff dashboard", "J07": "J07 Patient on the staff dashboard", "J08": "J08 Staff on the patient dashboard"}
def jtl(rows): w = csv.writer(open(os.path.join(T, "results", "run.jtl.tmp"), "w", newline="")); w.writerow(H); [w.writerow(r) for r in rows]; os.makedirs(os.path.join(T, "results", "run"), exist_ok=True); shutil.move(os.path.join(T, "results", "run.jtl.tmp"), os.path.join(T, "results", "run", "results.jtl"))
def R(label, code, ms=20, ok="true", msg=""): return [1, ms, label, code, "", "t", "text", ok, msg]
def good(ms9=100):
    rows = [R(LAB["J01"], 200), R(LAB["J02"], 200), R(LAB["J03"], 200), R(LAB["J04"], 200), R(LAB["J05"], 200), R(LAB["J06"], 401), R(LAB["J07"], 403), R(LAB["J08"], 403)]
    return rows + [R("J09 Staff dashboard repeated", 200, ms9) for i in range(30)]
def evid(pre=True, post=True, reqs=True, pf=True):
    for n, v in (("pre", pre), ("post", post), ("requests", reqs)): json.dump({"passed": v, "checks": [{"passed": v}]}, open(os.path.join(T, "evidence", f"verify-{n}.json"), "w"))
    open(os.path.join(T, "evidence", "preflight.txt"), "w").write("PRE-FLIGHT PASSED" if pf else "1 CHECK(S) FAILED")
def summ(name, rows, ok, **kw): jtl(rows); evid(**kw); expect(name, S, "-", ok, script="summarize.py")
summ("everything passed", good(), True)
summ("J09 mean above its limit (every request within the per-request cap)", good(ms9=450), False)
summ("J09 one request above the per-request cap", good()[:20] + [R("J09 Staff dashboard repeated", 200, 1600)] + good()[21:], False)
summ("J09 only 29 samples", good()[:-1], False)
summ("J05 failed an assertion (status 200)", good()[:4] + [R(LAB["J05"], 200, 20, "false", "statistics.upcoming = 8, expected 9")] + good()[5:], False)
summ("J06 answered 200", good()[:5] + [R(LAB["J06"], 200, 20, "false", "code")] + good()[6:], False)
summ("the database changed (post check failed)", good(), False, post=False)
summ("the server log did not show exactly 38 requests", good(), False, reqs=False)
summ("a 39th sample in the JTL", good() + [R(LAB["J01"], 200)], False)
shutil.rmtree(T, ignore_errors=True)
print("ALL VERIFIER AND SUMMARY CASES BEHAVE AS EXPECTED" if wrong == 0 else f"{wrong} CASE(S) BEHAVED UNEXPECTEDLY"); sys.exit(0 if wrong == 0 else 1)
