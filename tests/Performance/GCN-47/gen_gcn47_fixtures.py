#!/usr/bin/env python3
"""GCN-47 synthetic fixture generator. Produces, deterministically for a given 'now':
     fixtures/fixtures.json     what every scenario expects, computed by an INDEPENDENT oracle of the documented backend rules (never by calling the API)
     fixtures/seed-gcn47.sql    INSERT-only SQL for the isolated database (Appointments and AppointmentPayments; no status-change rows)
All data is synthetic: doctor GUIDs 47d1.../47d2..., patient GUIDs 47a0..., references CN-APT-DR47-NNNNN, no real person, number or credential.
No patient names or phones exist in this database (they come from the user-auth service, which is deliberately absent): the API must answer with contactsUnavailable.
Backend rules mirrored (DoctorAppointmentService):
  Sri Lanka calendar day = UTC + 5.5 h;  isToday = same SL date as 'now';  isUpcoming = SL date after today AND status Booked/Confirmed;  isCompleted = status Completed;
  isHistory = NoShow/Cancelled, or (not completed and (date before today or ended or unavailable));
  allowedStatuses: only Booked/Confirmed with a valid time range:  Booked -> Confirmed;  now >= start -> Completed;  now >= end -> NoShow.
Usage: gen_gcn47_fixtures.py [--out-dir DIR] [--now 2026-10-12T08:00:00Z] [--selftest]"""
import argparse, datetime as dt, json, os, sys

FMT = "%Y-%m-%dT%H:%M:%SZ"
STATUSES = {"Booked", "Confirmed", "Completed", "Cancelled", "NoShow"}
PAY_STATUS = {"Pending", "AwaitingBankTransferReceipt", "ReceiptUnderVerification", "AwaitingGatewayPayment", "Successful", "Failed"}
PAY_METHOD = {"Cash", "BankTransfer", "PaymentGateway"}
D1 = "47d10000-0000-4000-8000-000000000001"   # the signed-in doctor
D2 = "47d20000-0000-4000-8000-000000000002"   # another doctor
def patient(n): return f"47a00000-0000-4000-8000-{n:012d}"

def oracle(status, start, end, method, pstatus, now):
    sl = lambda t: (t + dt.timedelta(hours=5.5)).date()
    valid = start is not None and end > start
    today = sl(now); date = sl(start) if valid else None
    is_today = valid and date == today
    is_upcoming = valid and date > today and status in ("Booked", "Confirmed")
    is_completed = status == "Completed"
    is_history = status in ("NoShow", "Cancelled") or (not is_completed and (not valid or date < today or end <= now))
    allowed = []
    if valid and status in ("Booked", "Confirmed"):
        if status == "Booked": allowed.append("Confirmed")
        if now >= start: allowed.append("Completed")
        if now >= end: allowed.append("NoShow")
    pm = None if method is None else (method if method in PAY_METHOD else "Unavailable")
    ps = None if pstatus is None else (pstatus if pstatus in PAY_STATUS else "Unavailable")
    return {"status": status, "isToday": is_today, "isUpcoming": is_upcoming, "isCompleted": is_completed, "isHistory": is_history,
            "allowedStatuses": allowed, "paymentMethod": pm, "paymentStatus": ps}

# (id, days from today 00:00 UTC, hour, stored status, method, payment status, patient number)
D1_ROWS = [
    (47001, 4, 4, "Booked", "Cash", "Pending", 1),                          # JM-02 target: assigned appointment details
    (47002, 9, 5, "Booked", None, None, 2),                                 # JM-05 target: the one status update (Booked -> Confirmed)
    (47003, 6, 3, "Confirmed", "BankTransfer", "ReceiptUnderVerification", 1),
    (47004, -3, 5, "Booked", "PaymentGateway", "Failed", 3),                # ended and never confirmed: history, all three transitions offered
    (47005, -5, 4, "Completed", "Cash", "Successful", 3),
    (47006, -12, 3, "NoShow", None, None, 4),
    (47007, -8, 6, "Cancelled", None, None, 5),
    (47008, -20, 4, "Completed", "PaymentGateway", "Successful", 6),
]
D2_ROWS = [
    (47101, 5, 4, "Booked", "Cash", "Pending", 7),                          # JM-03 target: another doctor's appointment
    (47102, 7, 5, "Confirmed", None, None, 8),
    (47103, -6, 4, "Completed", "Cash", "Successful", 9),
]

def build(now):
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    rows, pays, doctors = [], [], {D1: [], D2: []}
    for owner, spec in ((D1, D1_ROWS), (D2, D2_ROWS)):
        for rid, days, hour, status, method, pstatus, pnum in spec:
            start = day0 + dt.timedelta(days=days, hours=hour); end = start + dt.timedelta(minutes=30)
            exp = oracle(status, start, end, method, pstatus, now)
            ref = f"CN-APT-DR47-{rid:05d}"
            rows.append({"Id": rid, "AppointmentReference": ref, "PatientId": patient(pnum), "DoctorId": owner, "DoctorName": "Dr Synthetic " + ("One" if owner == D1 else "Two"),
                         "DoctorAvailabilitySlotId": 470000000 + rid, "AppointmentStartUtc": start, "AppointmentEndUtc": end, "Status": status})
            if method is not None: pays.append({"AppointmentId": rid, "PatientId": patient(pnum), "Amount": "2700.00", "Method": method, "Status": pstatus})
            doctors[owner].append({"id": rid, "appointmentReference": ref, "patientId": patient(pnum), "appointmentStartUtc": start.strftime(FMT), "appointmentEndUtc": end.strftime(FMT),
                                   "updatedAtUtc": None, "patientName": None, "patientPhone": None, "contactsUnavailable": True, **exp})
    ordered = {k: sorted(v, key=lambda a: (a["appointmentStartUtc"], a["id"])) for k, v in doctors.items()}
    stats = {}
    for k, v in ordered.items():
        stats[k] = {"today": sum(a["isToday"] for a in v), "upcoming": sum(a["isUpcoming"] for a in v), "completed": sum(a["isCompleted"] for a in v), "patientCount": len({a["patientId"] for a in v})}
    return rows, pays, ordered, stats

def sql(rows, pays, now):
    q = lambda v: "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"
    ts = lambda d: d.strftime("%Y-%m-%d %H:%M:%S"); created = ts(now)
    out = ["-- GCN-47 synthetic seed (INSERT only). Generated " + now.strftime(FMT), "START TRANSACTION;"]
    cols = "`Id`, `AppointmentReference`, `PatientId`, `DoctorId`, `DoctorName`, `DoctorAvailabilitySlotId`, `AppointmentStartUtc`, `AppointmentEndUtc`, `Status`, `CreatedAtUtc`, `UpdatedAtUtc`"
    vals = ",".join("(" + ",".join([str(r["Id"]), q(r["AppointmentReference"]), q(r["PatientId"]), q(r["DoctorId"]), q(r["DoctorName"]), str(r["DoctorAvailabilitySlotId"]),
                                     q(ts(r["AppointmentStartUtc"])), q(ts(r["AppointmentEndUtc"])), q(r["Status"]), q(created), "NULL"]) + ")" for r in rows)
    out.append(f"INSERT INTO `Appointments` ({cols}) VALUES {vals};")
    pcols = "`AppointmentId`, `PatientId`, `Amount`, `Method`, `Status`, `CreatedAtUtc`, `UpdatedAtUtc`"
    pv = ",".join("(" + ",".join([str(p["AppointmentId"]), q(p["PatientId"]), p["Amount"], q(p["Method"]), q(p["Status"]), q(created), q(created)]) + ")" for p in pays)
    out.append(f"INSERT INTO `AppointmentPayments` ({pcols}) VALUES {pv};"); out.append("COMMIT;")
    return "\n".join(out) + "\n"

def selftest():
    now = dt.datetime(2026, 10, 12, 8, 0, 0); at = lambda d, h=0, m=0: now.replace(hour=0) + dt.timedelta(days=d, hours=h, minutes=m)
    cases = [   # (status, start, end) -> allowed statuses, per DoctorAppointmentService.AllowedStatuses and the developers' boundary tests
        (("Booked", at(4, 4), at(4, 4, 30)), []), (("Booked", at(4, 4), at(4, 4, 30)), ["Confirmed"]),
        (("Confirmed", at(4, 4), at(4, 4, 30)), []), (("Confirmed", at(0, 7), at(0, 9)), ["Completed"]),
        (("Confirmed", at(0, 5), at(0, 6)), ["Completed", "NoShow"]), (("Booked", at(-3, 5), at(-3, 5, 30)), ["Confirmed", "Completed", "NoShow"]),
        (("Completed", at(-5, 4), at(-5, 4, 30)), []), (("NoShow", at(-12, 3), at(-12, 3, 30)), []), (("Cancelled", at(-8, 6), at(-8, 6, 30)), []),
    ]
    expected = [["Confirmed"], ["Confirmed"], [], ["Completed"], ["Completed", "NoShow"], ["Confirmed", "Completed", "NoShow"], [], [], []]
    for (args, _), want in zip(cases, expected):
        got = oracle(args[0], args[1], args[2], None, None, now)["allowedStatuses"]; assert got == want, (args, got, want)
    r = oracle("Booked", at(4, 4), at(4, 4, 30), None, None, now); assert r["isUpcoming"] and not r["isToday"] and not r["isHistory"]
    r = oracle("Booked", at(-3, 5), at(-3, 5, 30), None, None, now); assert r["isHistory"] and not r["isUpcoming"]
    r = oracle("Completed", at(-5, 4), at(-5, 4, 30), None, None, now); assert r["isCompleted"] and not r["isHistory"]
    r = oracle("Confirmed", at(0, 5), at(0, 6), None, None, now); assert r["isToday"]      # today's date in Sri Lanka is the UTC date + 5.5 h
    print("oracle self-test: allowed statuses, upcoming, history, completed and today rules agree with the documented backend rules")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")); ap.add_argument("--now"); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(); selftest()
    if a.selftest: sys.exit(0)
    now = dt.datetime.strptime(a.now, FMT) if a.now else dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, microsecond=0)
    rows, pays, ordered, stats = build(now)
    assert len({r["Id"] for r in rows}) == len(rows) and len({r["AppointmentReference"] for r in rows}) == len(rows) and len({r["DoctorAvailabilitySlotId"] for r in rows}) == len(rows)
    for k, v in ordered.items():
        for x in v:   # sections must be stable for the validity window: nothing may be within 36 h of a calendar-day boundary or of 'now'
            assert abs((dt.datetime.strptime(x["appointmentStartUtc"], FMT) - now).total_seconds()) > 36 * 3600, x
    os.makedirs(a.out_dir, exist_ok=True)
    fx = {"generatedAtUtc": now.strftime(FMT), "validUntilUtc": (now + dt.timedelta(hours=36)).strftime(FMT), "synthetic": True,
          "doctors": {"D1": {"id": D1, "appointments": ordered[D1], "statistics": stats[D1]}, "D2": {"id": D2, "appointments": ordered[D2], "statistics": stats[D2]}},
          "patients": {f"P{n}": patient(n) for n in range(1, 10)},
          "targets": {"JM-02": {"doctor": "D1", "appointmentId": 47001}, "JM-03": {"doctor": "D1", "foreignAppointmentId": 47101}, "JM-04": {"role": "Patient", "patientId": patient(1)},
                      "JM-05": {"doctor": "D1", "appointmentId": 47002, "from": "Booked", "to": "Confirmed"}}}
    json.dump(fx, open(os.path.join(a.out_dir, "fixtures.json"), "w"), indent=1)
    open(os.path.join(a.out_dir, "seed-gcn47.sql"), "w").write(sql(rows, pays, now))
    print(f"doctors 2  appointments {len(rows)}  payments {len(pays)}  D1 statistics {stats[D1]}  valid until {fx['validUntilUtc']}")
