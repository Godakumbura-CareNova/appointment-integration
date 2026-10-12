#!/usr/bin/env python3
"""GCN-48 synthetic fixture generator. Produces, deterministically for a given 'now':
     fixtures/fixtures.json         what every scenario expects, computed OFFLINE by gcn48_version.py (a port of the documented backend rules; never by calling the API)
     fixtures/oracle-vectors.json   the same snapshots as plain JSON for the .NET oracle (gcn48_check_version.py compares them with the real backend code)
     fixtures/seed-gcn48.sql        INSERT-only SQL for the isolated database (Appointments and AppointmentPayments only; no cancellation, refund or reconciliation rows)
All data is synthetic: patients 48a1.../48a2..., doctor 48d1..., references CN-APT-CXL48-NNNNN, no real person, number or credential.
Usage: gen_gcn48_fixtures.py [--out-dir DIR] [--now 2026-10-12T08:00:00Z] [--selftest]"""
import argparse, datetime as dt, json, os, sys
from decimal import Decimal
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gcn48_version as V

FMT = "%Y-%m-%dT%H:%M:%SZ"
P1 = "48a10000-0000-4000-8000-000000000001"   # the signed-in patient of JM-01, JM-02, JM-05
P2 = "48a20000-0000-4000-8000-000000000002"   # another patient (owner of the JM-03 appointment)
DOC = "48d10000-0000-4000-8000-000000000001"  # the doctor identity used by JM-04 (and the doctor named on every appointment)
REASON = "GCN-48 JMeter synthetic QA cancellation"
# (id, patient, hours from now, status, method, payment status, amount, role in the plan)
ROWS = [
    (48001, P1, 96, "Booked", "Cash", "Pending", "1500.00", "JM-01 own unpaid appointment (also the JM-04 target)"),
    (48002, P1, 100, "Booked", "Cash", "Successful", "1500.00", "JM-02 restricted: cash already paid"),
    (48003, P1, 104, "Booked", "BankTransfer", "Successful", "2000.00", "decoy: must stay untouched"),
    (48004, P1, -48, "Completed", "Cash", "Successful", "1500.00", "decoy: must stay untouched"),
    (48005, P1, 72, "Booked", "BankTransfer", "Successful", "1500.00", "JM-05 verified bank transfer, 72 h before the start: the ONE cancellation"),
    (48006, P1, 120, "Booked", None, None, "0", "decoy: no payment selected"),
    (48101, P2, 96, "Booked", "Cash", "Pending", "1500.00", "JM-03 belongs to patient 2"),
    (48102, P2, 72, "Booked", "BankTransfer", "Successful", "1500.00", "decoy of patient 2"),
]
def build(now):
    appts, pays, vectors = [], [], []
    for rid, pat, hours, status, method, pstatus, amount, note in ROWS:
        start = (now + dt.timedelta(hours=hours)).replace(minute=0, second=0, microsecond=0); end = start + dt.timedelta(minutes=30)
        has_pay = method is not None
        snap = V.snapshot(AppointmentId=rid, PatientId=pat, Status=status, StartUtc=start, EndUtc=end, PaymentId=rid if has_pay else None, PaymentMethod=method, PaymentStatus=pstatus,
                          Amount=Decimal(amount), PaymentUpdatedAtUtc=now if has_pay else None)
        dec = V.evaluate(snap, now)
        appts.append({"id": rid, "appointmentReference": f"CN-APT-CXL48-{rid:05d}", "patientId": pat, "status": status, "startUtc": start.strftime(FMT), "endUtc": end.strftime(FMT),
                      "paymentMethod": method, "paymentStatus": pstatus, "amount": amount, "note": note,
                      "expected": {"allowed": dec["Allowed"], "reasonCode": dec["ReasonCode"], "message": dec["Message"], "refundOutcome": dec["RefundOutcome"],
                                   "refundAmount": float(Decimal(dec["RefundAmount"])), "requiresNoRefundAcknowledgement": dec["Ack"], "version": V.version(snap, dec)}})
        vectors.append(V.vector(snap, now))
        if has_pay: pays.append({"Id": rid, "AppointmentId": rid, "PatientId": pat, "Amount": amount, "Method": method, "Status": pstatus})
    return appts, pays, vectors

def sql(appts, pays, now):
    q = lambda v: "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"
    ts = lambda s: dt.datetime.strptime(s, FMT).strftime("%Y-%m-%d %H:%M:%S"); created = now.strftime("%Y-%m-%d %H:%M:%S")
    out = ["-- GCN-48 synthetic seed (INSERT only). Generated " + now.strftime(FMT), "START TRANSACTION;"]
    cols = "`Id`, `AppointmentReference`, `PatientId`, `DoctorId`, `DoctorName`, `DoctorAvailabilitySlotId`, `AppointmentStartUtc`, `AppointmentEndUtc`, `Status`, `CreatedAtUtc`, `UpdatedAtUtc`"
    vals = ",".join("(" + ",".join([str(a["id"]), q(a["appointmentReference"]), q(a["patientId"]), q(DOC), q("Dr Synthetic Cancel"), str(480000000 + a["id"]), q(ts(a["startUtc"])), q(ts(a["endUtc"])), q(a["status"]), q(created), "NULL"]) + ")" for a in appts)
    out.append(f"INSERT INTO `Appointments` ({cols}) VALUES {vals};")
    pcols = "`Id`, `AppointmentId`, `PatientId`, `Amount`, `Method`, `Status`, `CreatedAtUtc`, `UpdatedAtUtc`"
    pv = ",".join("(" + ",".join([str(p["Id"]), str(p["AppointmentId"]), q(p["PatientId"]), p["Amount"], q(p["Method"]), q(p["Status"]), q(created), q(created)]) + ")" for p in pays)
    out.append(f"INSERT INTO `AppointmentPayments` ({pcols}) VALUES {pv};"); out.append("COMMIT;")
    return "\n".join(out) + "\n"

def selftest():
    V.selftest(); now = dt.datetime(2026, 10, 12, 8, 0, 0); appts, pays, vectors = build(now); by = {a["id"]: a for a in appts}
    e = lambda i: by[i]["expected"]
    assert e(48001)["allowed"] and e(48001)["reasonCode"] == "Unpaid" and e(48001)["refundOutcome"] == "NotRequired" and e(48001)["refundAmount"] == 0
    assert not e(48002)["allowed"] and e(48002)["reasonCode"] == "CashAlreadyPaid"
    assert e(48005)["allowed"] and e(48005)["reasonCode"] == "RefundEligible" and e(48005)["refundOutcome"] == "Eligible" and e(48005)["refundAmount"] == 1500 and not e(48005)["requiresNoRefundAcknowledgement"]
    assert not e(48004)["allowed"] and e(48004)["reasonCode"] == "AppointmentNotEligible"
    assert len({a["expected"]["version"] for a in appts}) == len(appts), "versions must differ per appointment"
    assert all(len(a["expected"]["version"]) == 64 for a in appts) and len(pays) == 7 and len(appts) == 8
    # the JM-05 target is more than 8 hours before its start, with a wide margin for the 36 h validity window
    assert (dt.datetime.strptime(by[48005]["startUtc"], FMT) - now).total_seconds() / 3600 >= 36 + 8
    print("fixture self-test: expected decisions of the five scenarios agree with the documented rules")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")); ap.add_argument("--now"); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(); selftest()
    if a.selftest: sys.exit(0)
    now = dt.datetime.strptime(a.now, FMT) if a.now else dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, microsecond=0)
    appts, pays, vectors = build(now); os.makedirs(a.out_dir, exist_ok=True)
    fx = {"generatedAtUtc": now.strftime(FMT), "validUntilUtc": (now + dt.timedelta(hours=36)).strftime(FMT), "synthetic": True, "counts": {"appointments": len(appts), "payments": len(pays)},
          "actors": {"patient1": P1, "patient2": P2, "doctor": DOC}, "appointments": appts,
          "targets": {"JM-01": {"appointmentId": 48001, "actor": "patient1"}, "JM-02": {"appointmentId": 48002, "actor": "patient1"}, "JM-03": {"appointmentId": 48101, "actor": "patient1", "ownerActor": "patient2"},
                      "JM-04": {"appointmentId": 48001, "actor": "doctor", "role": "Doctor"},
                      "JM-05": {"appointmentId": 48005, "actor": "patient1", "reason": REASON, "expectedVersion": next(x for x in appts if x["id"] == 48005)["expected"]["version"], "refundAmount": 1500}}}
    json.dump(fx, open(os.path.join(a.out_dir, "fixtures.json"), "w"), indent=1)
    json.dump({"nowUtc": now.strftime(FMT), "vectors": vectors}, open(os.path.join(a.out_dir, "oracle-vectors.json"), "w"), indent=1)
    open(os.path.join(a.out_dir, "seed-gcn48.sql"), "w").write(sql(appts, pays, now))
    print(f"appointments {len(appts)}  payments {len(pays)}  valid until {fx['validUntilUtc']}  (JM-05 expectedVersion computed offline, not shown)")
