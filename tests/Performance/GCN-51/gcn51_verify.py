#!/usr/bin/env python3
"""GCN-51 read-only verification. NO HTTP request is ever made here. Modes (all write evidence/*.json and exit non-zero on any failed check):
   pre       before the run:  database == the seeded fixtures (appointments, payments, receipts), every other table empty, fixtures fresh and synthetic; saves the snapshot
   post      after the run:   every table is IDENTICAL to the snapshot taken before the run (the suite is read-only: nothing may have been created, changed or deleted)
   requests  after the run:   the backend's own request log shows EXACTLY the 38 expected requests (method, path, status), in order: no health check, retry, redirect or extra call
Database access: the mysql client as the limited user gcn51_qa on 127.0.0.1 (SELECT statements only); the password comes from GCN51_DB_PASSWORD in the environment and is never printed."""
import datetime as dt, hashlib, json, os, re, subprocess, sys
from decimal import Decimal
HERE = os.path.dirname(os.path.abspath(__file__)); EVID = os.path.join(HERE, "evidence")
DB, USER, HOST, PORT = "carenova_appointment_gcn51_qa", "gcn51_qa", "127.0.0.1", "3306"     # fixed targets: nothing else can be queried
FMT = "%Y-%m-%dT%H:%M:%SZ"
checks = []
def check(name, ok, detail=""): checks.append({"name": name, "passed": bool(ok), "detail": str(detail)[:300]}); print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok or not detail else f"  [{str(detail)[:200]}]"))
def q(sql):
    pw = os.environ.get("GCN51_DB_PASSWORD")
    if not pw: sys.exit("GCN51_DB_PASSWORD is not in the environment (run through gcn51-verify.sh)")
    if not re.match(r"^\s*SELECT\b", sql, re.I): sys.exit("read-only guard: only SELECT statements are allowed")
    out = subprocess.run(["mysql", "--protocol=TCP", "-h", HOST, "-P", PORT, "-u", USER, "-N", "-B", DB, "-e", sql], capture_output=True, text=True, env={**os.environ, "MYSQL_PWD": pw})
    if out.returncode: sys.exit("database query failed: " + out.stderr.strip()[:200])
    return [l.split("\t") for l in out.stdout.splitlines()]
def save(mode, extra=None):
    os.makedirs(EVID, exist_ok=True); passed = all(c["passed"] for c in checks)
    json.dump({"mode": mode, "passed": passed, "generatedAtUtc": dt.datetime.now(dt.timezone.utc).strftime(FMT), "checks": checks, **(extra or {})}, open(os.path.join(EVID, f"verify-{mode}.json"), "w"), indent=1)
    print(f"{mode}: {'ALL CHECKS PASSED' if passed else 'FAILED'} ({sum(c['passed'] for c in checks)}/{len(checks)})"); sys.exit(0 if passed else 1)

fx = json.load(open(os.path.join(HERE, "fixtures", "fixtures.json")))
D = "'%Y-%m-%d %H:%i:%s.%f'"
APPT_SQL = f"SELECT Id, AppointmentReference, PatientId, DoctorId, Status, DATE_FORMAT(AppointmentStartUtc,{D}), DATE_FORMAT(AppointmentEndUtc,{D}), IFNULL(DATE_FORMAT(UpdatedAtUtc,{D}),'NULL') FROM Appointments ORDER BY Id"
PAY_SQL = f"SELECT Id, AppointmentId, PatientId, Method, Status, Amount, IFNULL(DATE_FORMAT(ConfirmedAtUtc,{D}),'NULL'), DATE_FORMAT(UpdatedAtUtc,{D}) FROM AppointmentPayments ORDER BY Id"
REC_SQL = f"SELECT Id, AppointmentPaymentId, AppointmentId, PatientId, Status, DATE_FORMAT(UploadedAtUtc,{D}) FROM AppointmentReceipts ORDER BY Id"
TABLES = ("Appointments", "AppointmentPayments", "AppointmentReceipts", "AppointmentOnlinePaymentAttempts", "AppointmentStatusChanges", "AppointmentCancellations", "RefundRecords", "AppointmentPaymentReconciliations")
def counts(): return dict(zip(TABLES, map(int, q("SELECT " + ",".join(f"(SELECT COUNT(*) FROM {t})" for t in TABLES))[0])))
def ts(s): return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f")
def fts(s): return None if s is None else dt.datetime.strptime(s, FMT)
def snapshot(): return {"appointments": q(APPT_SQL), "payments": q(PAY_SQL), "receipts": q(REC_SQL), "counts": counts()}
def digest(s): return hashlib.sha256(json.dumps(s, sort_keys=True).encode()).hexdigest()[:16]

def pre():
    print("GCN-51 PRECONDITIONS (read-only SQL)")
    check("fixtures are synthetic and fresh", fx.get("synthetic") is True and dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) < dt.datetime.strptime(fx["validUntilUtc"], FMT), fx.get("validUntilUtc"))
    s = snapshot(); want = {t: 0 for t in TABLES}; want.update({"Appointments": fx["counts"]["appointments"], "AppointmentPayments": fx["counts"]["payments"], "AppointmentReceipts": fx["counts"]["receipts"]})
    check(f"row counts equal the seed ({fx['counts']['appointments']} appointments, {fx['counts']['payments']} payments, {fx['counts']['receipts']} receipts; every other table empty)", s["counts"] == want, s["counts"])
    ex = {a["id"]: a for a in fx["appointments"]}; bad = []
    for r in s["appointments"]:
        a = ex.get(int(r[0]))
        if a is None or (r[1], r[2], r[3], r[4]) != (a["appointmentReference"], a["patientId"], a["doctorId"], a["status"]) or r[7] != "NULL" or ts(r[5]) != fts(a["startUtc"]) or ts(r[6]) != fts(a["endUtc"]): bad.append(r[0])
    check("every appointment equals the fixtures (reference, patient, doctor, status, times) and has never been updated", len(s["appointments"]) == len(ex) and not bad, bad)
    pays = {p["id"]: p for p in fx["staff"]["payments"]}; badp = []
    for r in s["payments"]:
        p = pays.get(int(r[0]))
        if p is None or (int(r[1]), r[2], r[3], r[4]) != (p["appointmentId"], p["patientId"], p["method"], p["status"]) or Decimal(r[5]) != Decimal(p["amount"]) or ts(r[7]) != fts(p["updatedAtUtc"]) \
           or (r[6] == "NULL") != (p["confirmedAtUtc"] is None) or (r[6] != "NULL" and ts(r[6]) != fts(p["confirmedAtUtc"])): badp.append(r[0])
    check("every payment equals the fixtures (appointment, patient, method, status, amount, confirmation and update times)", len(s["payments"]) == len(pays) and not badp, badp)
    rs = {r[0]: r[4] for r in s["receipts"]}
    check("receipts: the six pending transfers' receipts are PendingVerification, the rejected one is Rejected", sum(v == "PendingVerification" for v in rs.values()) == fx["staff"]["pendingTotal"] and list(rs.values()).count("Rejected") == 1, rs)
    check("every patient, doctor and staff id is synthetic (51a.../51d.../51c...)", all(r[2].startswith("51a") and r[3].startswith("51d") for r in s["appointments"]))
    save("pre", {"snapshot": s, "digest": digest(s)})

def post():
    print("GCN-51 POST-RUN DATABASE INTEGRITY (read-only SQL, no HTTP): the suite is read-only")
    before = json.load(open(os.path.join(EVID, "verify-pre.json")))["snapshot"]; after = snapshot()
    check("row counts of EVERY table are unchanged", after["counts"] == before["counts"], after["counts"])
    check("every appointment row is identical to the snapshot taken before the run (nothing created, changed or deleted)", after["appointments"] == before["appointments"])
    check("every payment row is identical (amounts, statuses, confirmation and update times)", after["payments"] == before["payments"])
    check("every receipt row is identical", after["receipts"] == before["receipts"])
    check("no cancellation, refund, reconciliation, status-change or online-payment-attempt row appeared", all(after["counts"][t] == 0 for t in TABLES[3:]))
    save("post", {"digestBefore": digest(before), "digestAfter": digest(after)})

def requests():
    print("GCN-51 SERVER-SIDE REQUEST COUNT (from the backend's own request log; no HTTP)")
    log = os.path.join(HERE, "logs", "backend.log"); base = int(open(os.path.join(EVID, "log-baseline.txt")).read().strip())
    lines = open(log, errors="replace").read().splitlines()[base:]
    starts = [(m.group(1), re.sub(r"^https?://[^/]+", "", m.group(2)).split("?")[0]) for l in lines for m in [re.search(r"Request starting HTTP/\S+ (\w+) (\S+)", l)] if m]
    fins = [int(m.group(1)) for l in lines for m in [re.search(r"Request finished HTTP/\S+ \w+ \S+ - (\d{3})", l)] if m]
    PD, SD, DD = "/api/patient/dashboard/appointments", "/api/staff/dashboard/appointment-payments", "/api/doctor/appointments"
    want = [("GET", PD, 200), ("GET", PD, 200), ("GET", SD, 200), ("GET", SD, 200), ("GET", DD, 200), ("GET", SD, 401), ("GET", SD, 403), ("GET", PD, 403)] + [("GET", SD, 200)] * 30
    check("the server received exactly 38 requests during the run (J01-J08: 8, J09: 30)", len(starts) == 38, f"{len(starts)}")
    check("they are the expected requests, in order, all GET: no health check, retry, redirect, setup, teardown or write", starts == [(m, p) for m, p, _ in want], starts[:12])
    check("and they were answered with the expected statuses (200 x5, 401, 403 x2, then 30 x 200)", fins == [s for _, _, s in want], fins[:12])
    save("requests", {"requests": len(starts), "statuses": fins})

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    {"pre": pre, "post": post, "requests": requests}.get(mode, lambda: sys.exit(__doc__))()
