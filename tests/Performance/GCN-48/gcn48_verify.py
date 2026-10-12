#!/usr/bin/env python3
"""GCN-48 read-only verification. NO HTTP request is ever made here. Modes (all write evidence/*.json and exit non-zero on any failed check):
   pre       before the run:  database == the seeded fixtures, nothing cancelled yet, JM-05's target is still Booked with a verified bank transfer more than 8 hours before its start,
                              no cancellation, refund or reconciliation row exists, fixtures fresh and synthetic
   post      after the run:   JM-05 produced exactly ONE cancellation row and ONE manual-refund row (PendingManualProcessing) whose times equal the appointment's UpdatedAtUtc and the HTTP response;
                              every other row and every payment is byte-for-byte what the seed created
   requests  after the run:   the backend's own request log shows EXACTLY the five expected requests (method, path, status), in order: no health check, retry, redirect or extra call
Database access: the mysql client as the limited user gcn48_qa on 127.0.0.1 (SELECT statements only); the password comes from GCN48_DB_PASSWORD in the environment and is never printed."""
import datetime as dt, json, os, re, subprocess, sys
from decimal import Decimal
HERE = os.path.dirname(os.path.abspath(__file__)); EVID = os.path.join(HERE, "evidence")
DB, USER, HOST, PORT = "carenova_appointment_gcn48_qa", "gcn48_qa", "127.0.0.1", "3306"     # fixed targets: nothing else can be queried
FMT = "%Y-%m-%dT%H:%M:%SZ"
checks = []
def check(name, ok, detail=""): checks.append({"name": name, "passed": bool(ok), "detail": str(detail)[:300]}); print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok or not detail else f"  [{str(detail)[:200]}]"))

def q(sql):
    pw = os.environ.get("GCN48_DB_PASSWORD")
    if not pw: sys.exit("GCN48_DB_PASSWORD is not in the environment (run through gcn48-verify.sh)")
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
P1, P2, DOC = fx["actors"]["patient1"], fx["actors"]["patient2"], fx["actors"]["doctor"]
expected = {a["id"]: a for a in fx["appointments"]}
T5 = fx["targets"]["JM-05"]; TARGET = T5["appointmentId"]; FOREIGN = fx["targets"]["JM-03"]["appointmentId"]; REASON = T5["reason"]
APPT_SQL = "SELECT Id, AppointmentReference, PatientId, DoctorId, Status, DATE_FORMAT(AppointmentStartUtc,'%Y-%m-%d %H:%i:%s'), DATE_FORMAT(AppointmentEndUtc,'%Y-%m-%d %H:%i:%s'), IFNULL(DATE_FORMAT(UpdatedAtUtc,'%Y-%m-%d %H:%i:%s.%f'),'NULL') FROM Appointments ORDER BY Id"
PAY_SQL = "SELECT Id, AppointmentId, PatientId, Method, Status, Amount, DATE_FORMAT(CreatedAtUtc,'%Y-%m-%d %H:%i:%s.%f'), DATE_FORMAT(UpdatedAtUtc,'%Y-%m-%d %H:%i:%s.%f') FROM AppointmentPayments ORDER BY Id"
CANCEL_SQL = ("SELECT Id, AppointmentId, PatientId, PreviousStatus, IFNULL(Reason,'NULL'), IFNULL(PaymentId,'NULL'), IFNULL(PaymentMethod,'NULL'), IFNULL(PaymentStatus,'NULL'), PaymentAmount, RefundOutcome, RefundAmount, DecisionMessage, "
              "DATE_FORMAT(CancelledAtUtc,'%Y-%m-%d %H:%i:%s.%f') FROM AppointmentCancellations ORDER BY Id")
REFUND_SQL = "SELECT Id, CancellationId, Amount, Currency, Status, DATE_FORMAT(CreatedAtUtc,'%Y-%m-%d %H:%i:%s.%f') FROM RefundRecords ORDER BY Id"
KEYS = ("appointments", "payments", "receipts", "attempts", "statusChanges", "cancellations", "refunds", "reconciliations")
def counts():
    r = q("SELECT (SELECT COUNT(*) FROM Appointments),(SELECT COUNT(*) FROM AppointmentPayments),(SELECT COUNT(*) FROM AppointmentReceipts),(SELECT COUNT(*) FROM AppointmentOnlinePaymentAttempts),"
          "(SELECT COUNT(*) FROM AppointmentStatusChanges),(SELECT COUNT(*) FROM AppointmentCancellations),(SELECT COUNT(*) FROM RefundRecords),(SELECT COUNT(*) FROM AppointmentPaymentReconciliations)")[0]
    return dict(zip(KEYS, map(int, r)))

def pre():
    print("GCN-48 PRECONDITIONS (read-only SQL)")
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    check("fixtures are synthetic and fresh", fx.get("synthetic") is True and now < dt.datetime.strptime(fx["validUntilUtc"], FMT), fx.get("validUntilUtc"))
    c = counts(); want = {"appointments": fx["counts"]["appointments"], "payments": fx["counts"]["payments"], "receipts": 0, "attempts": 0, "statusChanges": 0, "cancellations": 0, "refunds": 0, "reconciliations": 0}
    check("row counts equal the seed (8 appointments, 7 payments; no receipts, attempts, doctor audit, CANCELLATION, REFUND or reconciliation rows)", c == want, c)
    rows = q(APPT_SQL); bad = []
    for r in rows:
        i = int(r[0]); a = expected.get(i)
        if a is None or (r[1], r[2], r[3]) != (a["appointmentReference"], a["patientId"], DOC) or r[4] != a["status"] or r[7] != "NULL" \
           or dt.datetime.strptime(r[5], "%Y-%m-%d %H:%M:%S") != dt.datetime.strptime(a["startUtc"], FMT) or dt.datetime.strptime(r[6], "%Y-%m-%d %H:%M:%S") != dt.datetime.strptime(a["endUtc"], FMT): bad.append(i)
    check("every appointment equals the fixtures (reference, patient, status, times) and has never been updated", len(rows) == len(expected) and not bad, bad)
    pays = q(PAY_SQL); badp = [p[0] for p in pays if not any(str(a["id"]) == p[1] and a["patientId"] == p[2] and a["paymentMethod"] == p[3] and a["paymentStatus"] == p[4] and Decimal(a["amount"]) == Decimal(p[5]) and p[0] == p[1] for a in fx["appointments"])]
    check("every payment equals the fixtures (appointment, patient, method, status, amount)", len(pays) == fx["counts"]["payments"] and not badp, badp)
    t = [r for r in rows if int(r[0]) == TARGET]; tp = [p for p in pays if int(p[1]) == TARGET]
    check(f"JM-05 target {TARGET} is Booked, patient 1's, never updated, with a Successful BankTransfer payment of 1500.00", len(t) == 1 and t[0][4] == "Booked" and t[0][2] == P1 and t[0][7] == "NULL" and len(tp) == 1 and (tp[0][3], tp[0][4], Decimal(tp[0][5])) == ("BankTransfer", "Successful", Decimal("1500.00")), (t, tp))
    check(f"JM-05 target starts more than 8 hours from now (refund-eligible window), margin {(dt.datetime.strptime(t[0][5], '%Y-%m-%d %H:%M:%S') - now).total_seconds() / 3600:.1f} h" if t else "JM-05 target start",
          bool(t) and (dt.datetime.strptime(t[0][5], "%Y-%m-%d %H:%M:%S") - now).total_seconds() > 8 * 3600)
    f = [r for r in rows if int(r[0]) == FOREIGN]
    check(f"JM-03 target {FOREIGN} exists and belongs to patient 2, not to patient 1", len(f) == 1 and f[0][2] == P2 and f[0][2] != P1, f)
    check("every patient and doctor id is synthetic (48a1.../48a2.../48d1...)", all(r[2].startswith(("48a10000-", "48a20000-")) and r[3].startswith("48d10000-") for r in rows))
    save("pre", {"snapshotAppointments": rows, "snapshotPayments": pays, "counts": c})

def post():
    print("GCN-48 POST-RUN DATABASE AND REFUND-RECORD INTEGRITY (read-only SQL, no HTTP)")
    pre_snap = json.load(open(os.path.join(EVID, "verify-pre.json")))
    resp_file = os.path.join(EVID, "jm05-response.json"); check("the JM-05 response evidence exists", os.path.exists(resp_file))
    resp = json.load(open(resp_file)) if os.path.exists(resp_file) else {}
    check("JM-05 evidence: HTTP 200, the target appointment, Cancelled, refund Eligible 1500, PendingManualProcessing",
          str(resp.get("httpStatus")) == "200" and resp.get("appointmentId") == TARGET and resp.get("status") == "Cancelled" and resp.get("refundOutcome") == "Eligible"
          and Decimal(str(resp.get("refundAmount", -1))) == Decimal("1500") and resp.get("refundStatus") == "PendingManualProcessing", resp)
    c = counts(); before = pre_snap["counts"]
    check("row counts: appointments, payments, receipts, attempts, doctor audit and reconciliations unchanged; exactly ONE cancellation row and ONE refund row", c == {**before, "cancellations": 1, "refunds": 1}, c)
    cl = q(CANCEL_SQL); row = cl[0] if len(cl) == 1 else None
    check("the cancellation row: appointment, patient 1, previous status Booked, the reason sent, the paid bank-transfer payment, Eligible refund of 1500.00, the decision message",
          bool(row) and (int(row[1]), row[2], row[3], row[4], int(row[5]), row[6], row[7]) == (TARGET, P1, "Booked", REASON, TARGET, "BankTransfer", "Successful")
          and Decimal(row[8]) == Decimal("1500") and row[9] == "Eligible" and Decimal(row[10]) == Decimal("1500") and row[11] == expected[TARGET]["expected"]["message"], cl)
    cancelled = ts(row[12]) if row else None
    rf = q(REFUND_SQL); rrow = rf[0] if len(rf) == 1 else None
    check("the refund record: linked to that cancellation, 1500.00 LKR, PendingManualProcessing, created at the cancellation time",
          bool(row and rrow) and int(rrow[1]) == int(row[0]) and Decimal(rrow[2]) == Decimal("1500") and rrow[3] == "LKR" and rrow[4] == "PendingManualProcessing" and ts(rrow[5]) == cancelled, rf)
    appt = {int(r[0]): r for r in q(APPT_SQL)}; t = appt.get(TARGET)
    check("the appointment is now Cancelled with UpdatedAtUtc set", bool(t) and t[4] == "Cancelled" and t[7] != "NULL", t)
    check("cancellation CancelledAtUtc == Appointments.UpdatedAtUtc (exact, to the microsecond)", bool(t and row) and ts(t[7]) == cancelled, (t[7] if t else None, row[12] if row else None))
    check("the HTTP response cancelledAtUtc == the stored CancelledAtUtc (to the microsecond)", bool(row and resp.get("cancelledAtUtc")) and iso(resp["cancelledAtUtc"]) == cancelled, (resp.get("cancelledAtUtc"), row[12] if row else None))
    snap = {int(r[0]): r for r in pre_snap["snapshotAppointments"]}
    others = [i for i in snap if i != TARGET]; changed_rows = [i for i in others if appt.get(i) != snap[i]]
    check("the other 7 appointments are identical to the seed (status, times, UpdatedAtUtc NULL), including all of patient 2's", not changed_rows and all(appt[i][7] == "NULL" for i in others), changed_rows)
    check("no cancellation or refund row exists for any other appointment", all(int(r[1]) == TARGET for r in cl))
    check("all 7 payments are identical to the seed (the cancelled appointment's payment is still Successful BankTransfer, untouched)", q(PAY_SQL) == pre_snap["snapshotPayments"])
    save("post")

def requests():
    print("GCN-48 SERVER-SIDE REQUEST COUNT (from the backend's own request log; no HTTP)")
    log = os.path.join(HERE, "logs", "backend.log"); base = int(open(os.path.join(EVID, "log-baseline.txt")).read().strip())
    lines = open(log, errors="replace").read().splitlines()[base:]
    starts = [(m.group(1), re.sub(r"^https?://[^/]+", "", m.group(2)).split("?")[0]) for l in lines for m in [re.search(r"Request starting HTTP/\S+ (\w+) (\S+)", l)] if m]
    fins = [(int(m.group(1))) for l in lines for m in [re.search(r"Request finished HTTP/\S+ \w+ \S+ - (\d{3})", l)] if m]
    path = lambda i: f"/api/patient/appointments/{i}/cancellation"
    want = [("GET", path(fx["targets"]["JM-01"]["appointmentId"])), ("GET", path(fx["targets"]["JM-02"]["appointmentId"])), ("GET", path(FOREIGN)), ("GET", path(fx["targets"]["JM-04"]["appointmentId"])), ("POST", path(TARGET))]
    check("the server received exactly 5 requests during the run", len(starts) == 5, f"{len(starts)}: {starts}")
    check("they are the five expected requests, in order (4 GET + 1 POST): no health check, retry, redirect, setup or teardown call", starts == want, starts)
    check("and they were answered 200, 200, 404, 403, 200", fins == [200, 200, 404, 403, 200], fins)
    save("requests", {"requests": starts, "statuses": fins})

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    {"pre": pre, "post": post, "requests": requests}.get(mode, lambda: sys.exit(__doc__))()
