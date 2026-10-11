#!/usr/bin/env python3
"""GCN-47 read-only verification. NO HTTP request is ever made here. Modes (all write evidence/*.json and exit non-zero on any failed check):
   pre       before the run:  database == the seeded fixtures, nothing changed yet, the JM-05 target is still Booked, no audit row exists, fixtures fresh and synthetic
   post      after the run:   JM-05 produced exactly ONE audit row (Booked -> Confirmed, doctor 1) whose time equals the appointment's UpdatedAtUtc and the HTTP response;
                              every other row, payment, receipt and attempt is byte-for-byte what the seed created
   requests  after the run:   the backend's own request log shows EXACTLY the five expected requests (method, path, status), in order: no health check, retry, redirect or extra call
Database access: the mysql client as the limited user gcn47_qa on 127.0.0.1 (SELECT statements only); the password comes from GCN47_DB_PASSWORD in the environment and is never printed."""
import datetime as dt, json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); EVID = os.path.join(HERE, "evidence")
DB, USER, HOST, PORT = "carenova_appointment_gcn47_qa", "gcn47_qa", "127.0.0.1", "3306"     # fixed targets: nothing else can be queried
FMT = "%Y-%m-%dT%H:%M:%SZ"
checks = []
def check(name, ok, detail=""): checks.append({"name": name, "passed": bool(ok), "detail": str(detail)[:300]}); print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok or not detail else f"  [{str(detail)[:200]}]"))

def q(sql):
    pw = os.environ.get("GCN47_DB_PASSWORD")
    if not pw: sys.exit("GCN47_DB_PASSWORD is not in the environment (run through gcn47-verify.sh)")
    if not re.match(r"^\s*SELECT\b", sql, re.I): sys.exit("read-only guard: only SELECT statements are allowed")
    out = subprocess.run(["mysql", "--protocol=TCP", "-h", HOST, "-P", PORT, "-u", USER, "-N", "-B", DB, "-e", sql], capture_output=True, text=True, env={**os.environ, "MYSQL_PWD": pw})
    if out.returncode: sys.exit("database query failed: " + out.stderr.strip()[:200])
    return [l.split("\t") for l in out.stdout.splitlines()]
def ts(v):   # MySQL datetime(6) text -> datetime (microseconds)
    if v in ("NULL", None): return None
    return dt.datetime.strptime(v, "%Y-%m-%d %H:%M:%S.%f") if "." in v else dt.datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
def iso(v):  # response timestamp (up to 7 fractional digits) -> datetime truncated to microseconds
    m = re.match(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,7}))?Z$", v); assert m, v
    return dt.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(microsecond=int((m.group(2) or "0").ljust(7, "0")[:6]))
def save(mode, extra=None):
    os.makedirs(EVID, exist_ok=True); passed = all(c["passed"] for c in checks)
    json.dump({"mode": mode, "passed": passed, "generatedAtUtc": dt.datetime.now(dt.timezone.utc).strftime(FMT), "checks": checks, **(extra or {})}, open(os.path.join(EVID, f"verify-{mode}.json"), "w"), indent=1)
    print(f"{mode}: {'ALL CHECKS PASSED' if passed else 'FAILED'} ({sum(c['passed'] for c in checks)}/{len(checks)})"); sys.exit(0 if passed else 1)

fx = json.load(open(os.path.join(HERE, "fixtures", "fixtures.json")))
D1, D2 = fx["doctors"]["D1"]["id"], fx["doctors"]["D2"]["id"]
expected = {a["id"]: (a, o) for o, d in ((D1, fx["doctors"]["D1"]), (D2, fx["doctors"]["D2"])) for a in d["appointments"]}
TARGET = fx["targets"]["JM-05"]["appointmentId"]; FOREIGN = fx["targets"]["JM-03"]["foreignAppointmentId"]
APPT_SQL = "SELECT Id, AppointmentReference, PatientId, DoctorId, Status, DATE_FORMAT(AppointmentStartUtc,'%Y-%m-%d %H:%i:%s'), DATE_FORMAT(AppointmentEndUtc,'%Y-%m-%d %H:%i:%s'), IFNULL(DATE_FORMAT(UpdatedAtUtc,'%Y-%m-%d %H:%i:%s.%f'),'NULL') FROM Appointments ORDER BY Id"
PAY_SQL = "SELECT Id, AppointmentId, PatientId, Method, Status, Amount, DATE_FORMAT(UpdatedAtUtc,'%Y-%m-%d %H:%i:%s.%f') FROM AppointmentPayments ORDER BY Id"
def counts():
    r = q("SELECT (SELECT COUNT(*) FROM Appointments),(SELECT COUNT(*) FROM AppointmentPayments),(SELECT COUNT(*) FROM AppointmentReceipts),(SELECT COUNT(*) FROM AppointmentOnlinePaymentAttempts),(SELECT COUNT(*) FROM AppointmentStatusChanges)")[0]
    return dict(zip(("appointments", "payments", "receipts", "attempts", "statusChanges"), map(int, r)))

def pre():
    print("GCN-47 PRECONDITIONS (read-only SQL)")
    check("fixtures are synthetic and fresh", fx.get("synthetic") is True and dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) < dt.datetime.strptime(fx["validUntilUtc"], FMT), fx.get("validUntilUtc"))
    c = counts(); want = {"appointments": len(expected), "payments": 7, "receipts": 0, "attempts": 0, "statusChanges": 0}
    check("row counts equal the seed (11 appointments, 7 payments, no receipts, no attempts, NO audit rows)", c == want, c)
    rows = q(APPT_SQL); bad = []
    for r in rows:
        i = int(r[0]); a, owner = expected.get(i, (None, None))
        if a is None or (r[1], r[2], r[3]) != (a["appointmentReference"], a["patientId"], owner) or r[4] != a["status"] or r[7] != "NULL" \
           or dt.datetime.strptime(r[5], "%Y-%m-%d %H:%M:%S") != dt.datetime.strptime(a["appointmentStartUtc"], FMT) or dt.datetime.strptime(r[6], "%Y-%m-%d %H:%M:%S") != dt.datetime.strptime(a["appointmentEndUtc"], FMT): bad.append(i)
    check("every appointment equals the fixtures (reference, patient, doctor, status, times) and has never been updated", len(rows) == len(expected) and not bad, bad)
    t = [r for r in rows if int(r[0]) == TARGET]
    check(f"JM-05 target {TARGET} is Booked, owned by doctor 1 and was never updated", len(t) == 1 and t[0][4] == "Booked" and t[0][3] == D1 and t[0][7] == "NULL", t)
    f = [r for r in rows if int(r[0]) == FOREIGN]
    check(f"JM-03 target {FOREIGN} exists and belongs to doctor 2, not to doctor 1", len(f) == 1 and f[0][3] == D2 and f[0][3] != D1, f)
    check("every doctor and patient id is synthetic (47d1.../47d2.../47a0...)", all(r[3].startswith(("47d10000-", "47d20000-")) and r[2].startswith("47a00000-") for r in rows))
    save("pre", {"snapshotAppointments": rows, "snapshotPayments": q(PAY_SQL), "counts": c})

def post():
    print("GCN-47 POST-RUN DATABASE AND AUDIT INTEGRITY (read-only SQL, no HTTP)")
    pre_snap = json.load(open(os.path.join(EVID, "verify-pre.json")))
    resp_file = os.path.join(EVID, "jm05-response.json"); check("the JM-05 response evidence exists", os.path.exists(resp_file))
    resp = json.load(open(resp_file)) if os.path.exists(resp_file) else {}
    check("JM-05 evidence: HTTP 200, the target appointment, status Confirmed", str(resp.get("httpStatus")) == "200" and resp.get("id") == TARGET and resp.get("status") == "Confirmed", resp)
    c = counts(); before = pre_snap["counts"]
    check("row counts: appointments, payments, receipts and attempts unchanged; exactly ONE audit row", c == {**before, "statusChanges": 1}, c)
    audit = q("SELECT Id, AppointmentId, DoctorId, PreviousStatus, NewStatus, DATE_FORMAT(ChangedAtUtc,'%Y-%m-%d %H:%i:%s.%f') FROM AppointmentStatusChanges ORDER BY Id")
    row = audit[0] if len(audit) == 1 else None
    check("the audit row: appointment, doctor 1, Booked -> Confirmed", bool(row) and (int(row[1]), row[2], row[3], row[4]) == (TARGET, D1, "Booked", "Confirmed"), audit)
    changed = ts(row[5]) if row else None
    appt = {int(r[0]): r for r in q(APPT_SQL)}; t = appt.get(TARGET)
    check("the appointment is now Confirmed with UpdatedAtUtc set", bool(t) and t[4] == "Confirmed" and t[7] != "NULL", t)
    check("audit ChangedAtUtc == Appointments.UpdatedAtUtc (exact, to the microsecond)", bool(t and row) and ts(t[7]) == changed, (t[7] if t else None, row[5] if row else None))
    check("the HTTP response updatedAtUtc == the stored UpdatedAtUtc (to the microsecond)", bool(t and resp.get("updatedAtUtc")) and iso(resp["updatedAtUtc"]) == ts(t[7]), (resp.get("updatedAtUtc"), t[7] if t else None))
    snap = {int(r[0]): r for r in pre_snap["snapshotAppointments"]}
    others = [i for i in snap if i != TARGET]; changed_rows = [i for i in others if appt.get(i) != snap[i]]
    check("the other 10 appointments are identical to the seed (status, times, UpdatedAtUtc NULL), including all of doctor 2's", not changed_rows and all(appt[i][7] == "NULL" for i in others), changed_rows)
    check("no audit row exists for any other appointment", all(int(r[1]) == TARGET for r in audit))
    check("all payments are identical to the seed", q(PAY_SQL) == pre_snap["snapshotPayments"])
    save("post")

def requests():
    print("GCN-47 SERVER-SIDE REQUEST COUNT (from the backend's own request log; no HTTP)")
    log = os.path.join(HERE, "logs", "backend.log"); base = int(open(os.path.join(EVID, "log-baseline.txt")).read().strip())
    lines = open(log, errors="replace").read().splitlines()[base:]
    starts = [(m.group(1), re.sub(r"^https?://[^/]+", "", m.group(2)).split("?")[0]) for l in lines for m in [re.search(r"Request starting HTTP/\S+ (\w+) (\S+)", l)] if m]
    fins = [(int(m.group(1))) for l in lines for m in [re.search(r"Request finished HTTP/\S+ \w+ \S+ - (\d{3})", l)] if m]
    want = [("GET", "/api/doctor/appointments"), ("GET", f"/api/doctor/appointments/{fx['targets']['JM-02']['appointmentId']}"), ("GET", f"/api/doctor/appointments/{FOREIGN}"),
            ("GET", "/api/doctor/appointments"), ("PATCH", f"/api/doctor/appointments/{TARGET}/status")]
    check("the server received exactly 5 requests during the run", len(starts) == 5, f"{len(starts)}: {starts}")
    check("they are the five expected requests, in order (4 GET + 1 PATCH): no health check, retry, redirect, setup or teardown call", starts == want, starts)
    check("and they were answered 200, 200, 404, 403, 200", fins == [200, 200, 404, 403, 200], fins)
    save("requests", {"requests": starts, "statuses": fins})

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    {"pre": pre, "post": post, "requests": requests}.get(mode, lambda: sys.exit(__doc__))()
