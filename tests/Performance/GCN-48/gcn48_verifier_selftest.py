#!/usr/bin/env python3
"""Offline self-test of gcn48_verify.py with a FAKE mysql client: no database, no server, no network. Builds a consistent 'seeded' state from freshly generated fixtures, then checks that the
verifier ACCEPTS the correct states and REJECTS every deliberately corrupted one (pre, post and request-log modes). Exit 1 if any case behaves differently from what is expected."""
import copy, datetime as dt, json, os, shutil, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); T = tempfile.mkdtemp(prefix="gcn48-verifier-test-")
FAKE = '''#!/usr/bin/env python3
import json, os, sys
a = sys.argv; sql = a[a.index("-e") + 1]; st = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "state.json")))
def emit(rows):
    for r in rows: print("\\t".join(str(x) for x in r))
if sql.startswith("SELECT (SELECT COUNT(*) FROM Appointments)"): emit([st["counts"]])
elif "FROM AppointmentCancellations ORDER" in sql: emit(st["cancellations"])
elif "FROM RefundRecords ORDER" in sql: emit(st["refunds"])
elif "FROM AppointmentPayments ORDER" in sql: emit(st["payments"])
elif "FROM Appointments ORDER" in sql: emit(st["appointments"])
else: sys.exit("fake mysql: unexpected query " + sql[:60])
'''
os.makedirs(os.path.join(T, "bin")); open(os.path.join(T, "bin", "mysql"), "w").write(FAKE); os.chmod(os.path.join(T, "bin", "mysql"), 0o755)
for d in ("fixtures", "evidence", "logs"): os.makedirs(os.path.join(T, d))
shutil.copy(os.path.join(HERE, "gcn48_verify.py"), T)
subprocess.run([sys.executable, os.path.join(HERE, "gen_gcn48_fixtures.py"), "--out-dir", os.path.join(T, "fixtures")], check=True, capture_output=True)
FX = json.load(open(os.path.join(T, "fixtures", "fixtures.json"))); ENV = {**os.environ, "PATH": os.path.join(T, "bin") + os.pathsep + os.environ["PATH"], "GCN48_DB_PASSWORD": "offline-dummy"}
P1, DOC = FX["actors"]["patient1"], FX["actors"]["doctor"]; REASON = FX["targets"]["JM-05"]["reason"]
def f(s): return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d %H:%M:%S")
NOW = dt.datetime.strptime(FX["generatedAtUtc"], "%Y-%m-%dT%H:%M:%SZ"); G = NOW.strftime("%Y-%m-%d %H:%M:%S.000000")
def seeded():
    ap = [[a["id"], a["appointmentReference"], a["patientId"], DOC, a["status"], f(a["startUtc"]), f(a["endUtc"]), "NULL"] for a in FX["appointments"]]
    pay = [[a["id"], a["id"], a["patientId"], a["paymentMethod"], a["paymentStatus"], a["amount"], G, G] for a in FX["appointments"] if a["paymentMethod"]]
    return {"appointments": ap, "payments": pay, "cancellations": [], "refunds": [], "counts": [len(ap), len(pay), 0, 0, 0, 0, 0, 0]}
def run(state, mode):
    json.dump(state, open(os.path.join(T, "state.json"), "w"))
    r = subprocess.run([sys.executable, os.path.join(T, "gcn48_verify.py"), mode], capture_output=True, text=True, env=ENV, cwd=T); return r.returncode, r.stdout
wrong = 0
def expect(name, state, mode, ok):
    global wrong; rc, out = run(state, mode); good = (rc == 0) == ok; wrong += not good
    fails = [l.strip()[6:90] for l in out.splitlines() if l.strip().startswith("FAIL")][:1]
    print(("OK    " if good else "WRONG ") + f"{mode:4} {name:78}" + (" -> rejected: " + fails[0] if rc and fails else (" -> accepted" if rc == 0 else " -> rejected")))
print("-- pre (before the run) --")
S = seeded(); expect("the seeded state", S, "pre", True)
def mut(fn):
    s = copy.deepcopy(S); fn(s); return s
expect("an appointment status already changed", mut(lambda s: s["appointments"][0].__setitem__(4, "Cancelled")), "pre", False)
expect("an appointment already updated (UpdatedAtUtc set)", mut(lambda s: s["appointments"][1].__setitem__(7, G)), "pre", False)
expect("a cancellation row already exists (not a fresh database)", mut(lambda s: s["counts"].__setitem__(5, 1)), "pre", False)
expect("a refund row already exists", mut(lambda s: s["counts"].__setitem__(6, 1)), "pre", False)
expect("a reconciliation row exists", mut(lambda s: s["counts"].__setitem__(7, 1)), "pre", False)
expect("a doctor audit row exists", mut(lambda s: s["counts"].__setitem__(4, 1)), "pre", False)
expect("a payment amount differs", mut(lambda s: s["payments"][0].__setitem__(5, "1.00")), "pre", False)
expect("the JM-05 payment is not Successful", mut(lambda s: s["payments"][[p[0] for p in s["payments"]].index(48005)].__setitem__(4, "Pending")), "pre", False)
soon = (dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
expect("the JM-05 appointment starts in 3 hours (not more than 8)", mut(lambda s: s["appointments"][[a[0] for a in s["appointments"]].index(48005)].__setitem__(5, soon)), "pre", False)
expect("the JM-03 appointment belongs to patient 1", mut(lambda s: s["appointments"][[a[0] for a in s["appointments"]].index(48101)].__setitem__(2, P1)), "pre", False)
expect("a non-synthetic patient id", mut(lambda s: s["appointments"][0].__setitem__(2, "11111111-1111-1111-1111-111111111111")), "pre", False)
expect("an appointment is missing", mut(lambda s: (s["appointments"].pop(), s["counts"].__setitem__(0, 7))), "pre", False)
run(S, "pre")                                   # saves evidence/verify-pre.json for the post cases
print("-- post (after the run) --")
CT = NOW + dt.timedelta(minutes=10, microseconds=123456); C = CT.strftime("%Y-%m-%d %H:%M:%S.%f"); ISO = CT.strftime("%Y-%m-%dT%H:%M:%S.123456") + "0Z"
a5 = next(a for a in FX["appointments"] if a["id"] == 48005)
def after():
    s = copy.deepcopy(S); i = [a[0] for a in s["appointments"]].index(48005); s["appointments"][i][4] = "Cancelled"; s["appointments"][i][7] = C
    s["cancellations"] = [[1, 48005, P1, "Booked", REASON, 48005, "BankTransfer", "Successful", "1500.00", "Eligible", "1500.00", a5["expected"]["message"], C]]
    s["refunds"] = [[1, 1, "1500.00", "LKR", "PendingManualProcessing", C]]; s["counts"][5] = 1; s["counts"][6] = 1; return s
def evidence(**o):
    d = {"appointmentId": 48005, "status": "Cancelled", "cancelledAtUtc": ISO, "refundOutcome": "Eligible", "refundAmount": 1500.0, "refundStatus": "PendingManualProcessing", "reason": REASON, "httpStatus": "200"}; d.update(o)
    json.dump(d, open(os.path.join(T, "evidence", "jm05-response.json"), "w"))
def post(name, fn, ok, ev=None):
    s = after(); fn(s); evidence(**(ev or {})); expect(name, s, "post", ok)
post("the correct final state", lambda s: None, True)
post("a second cancellation row", lambda s: (s["cancellations"].append([2] + s["cancellations"][0][1:]), s["counts"].__setitem__(5, 2)), False)
post("the cancellation belongs to another patient", lambda s: s["cancellations"][0].__setitem__(2, "48a20000-0000-4000-8000-000000000002"), False)
post("the stored reason differs", lambda s: s["cancellations"][0].__setitem__(4, "other"), False)
post("the stored refund is 1000.00", lambda s: s["cancellations"][0].__setitem__(10, "1000.00"), False)
post("the stored outcome is NotEligible", lambda s: s["cancellations"][0].__setitem__(9, "NotEligible"), False)
post("the refund record has the wrong status", lambda s: s["refunds"][0].__setitem__(4, "Refunded"), False)
post("the refund record has the wrong amount", lambda s: s["refunds"][0].__setitem__(2, "1000.00"), False)
post("the refund record is missing", lambda s: (s["refunds"].clear(), s["counts"].__setitem__(6, 0)), False)
post("the refund record points at another cancellation", lambda s: s["refunds"][0].__setitem__(1, 99), False)
post("the appointment is still Booked", lambda s: s["appointments"][[a[0] for a in s["appointments"]].index(48005)].__setitem__(4, "Booked"), False)
post("appointment UpdatedAtUtc differs from the cancellation time", lambda s: s["appointments"][[a[0] for a in s["appointments"]].index(48005)].__setitem__(7, G), False)
post("the response timestamp differs from the stored one", lambda s: None, False, ev={"cancelledAtUtc": "2026-10-12T00:00:00.1234560Z"})
post("another appointment was changed", lambda s: s["appointments"][0].__setitem__(4, "Cancelled"), False)
post("a payment was changed", lambda s: s["payments"][0].__setitem__(4, "Failed"), False)
post("a reconciliation row appeared", lambda s: s["counts"].__setitem__(7, 1), False)
post("a doctor audit row appeared", lambda s: s["counts"].__setitem__(4, 1), False)
post("the evidence says refundStatus is missing", lambda s: None, False, ev={"refundStatus": None})
post("the evidence says HTTP 409", lambda s: None, False, ev={"httpStatus": "409"})
os.remove(os.path.join(T, "evidence", "jm05-response.json")); expect("the JM-05 response evidence file is missing", after(), "post", False)
post("re-run on an already cancelled database (pre snapshot says nothing cancelled, counts say two)", lambda s: s["counts"].__setitem__(5, 2), False)
print("-- requests (the backend's own log) --")
base = 8; open(os.path.join(T, "evidence", "log-baseline.txt"), "w").write(str(base)); pre_lines = ["info: startup"] * base
def starts(m, p, st=200): return [f"info: Microsoft.AspNetCore.Hosting.Diagnostics[1]", f"      Request starting HTTP/1.1 {m} http://localhost:5248{p} - - -", f"info: Microsoft.AspNetCore.Hosting.Diagnostics[2]",
                                  f"      Request finished HTTP/1.1 {m} http://localhost:5248{p} - {st} - application/json;+charset=utf-8 5.0ms"]
P = lambda i: f"/api/patient/appointments/{i}/cancellation"
GOOD = [("GET", P(48001), 200), ("GET", P(48002), 200), ("GET", P(48101), 404), ("GET", P(48001), 403), ("POST", P(48005), 200)]
def log(reqs, name, ok, extra=None):
    lines = list(pre_lines) + sum((starts(*r) for r in reqs), []) + (extra or [])
    open(os.path.join(T, "logs", "backend.log"), "w").write("\n".join(lines) + "\n"); expect(name, S, "requests", ok)
log(GOOD, "exactly the five expected requests", True)
log(GOOD + [("GET", "/health", 200)], "a sixth request (health check)", False)
log(GOOD + [("POST", P(48005), 200)], "a repeated POST (retry)", False)
log(GOOD[:4], "only four requests", False)
log([GOOD[1], GOOD[0]] + GOOD[2:], "the first two requests swapped", False)
log(GOOD[:2] + [("GET", P(48101), 200)] + GOOD[3:], "JM-03 answered 200 instead of 404", False)
log(GOOD[:3] + [("GET", P(48001), 401)] + GOOD[4:], "JM-04 answered 401 instead of 403", False)
log(GOOD[:4] + [("PATCH", P(48005), 200)], "a PATCH instead of the POST", False)
log([("GET", "/api/patient/appointments/48001/cancellation", 200), ("GET", P(48002), 200), ("GET", P(48101), 404), ("GET", P(48001), 403), ("POST", P(48005), 200)], "the five requests with different path text", True)
shutil.rmtree(T, ignore_errors=True)
print("ALL VERIFIER CASES BEHAVE AS EXPECTED" if wrong == 0 else f"{wrong} CASE(S) BEHAVED UNEXPECTEDLY"); sys.exit(0 if wrong == 0 else 1)
