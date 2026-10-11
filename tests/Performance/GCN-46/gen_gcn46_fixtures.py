#!/usr/bin/env python3
"""GCN-46 synthetic fixture generator. Produces, deterministically for a given 'now':
     fixtures/fixtures.json     what every JMeter scenario expects (computed by an INDEPENDENT oracle of the documented backend rules, not by calling the API)
     fixtures/seed-gcn46.sql    INSERT-only SQL for the isolated database (Appointments and AppointmentPayments)
All data is synthetic: patient and doctor GUIDs of the form 46a0.../46d0..., references CN-APT-<key>-NNN, no real person, no real credential.
Backend rules mirrored (PatientAppointmentService): status Completed/Cancelled -> Previous; unknown status or invalid time range -> Unavailable;
otherwise Previous when the end time has passed, else Upcoming; unknown stored payment values are reported as 'Unavailable';
canPay = Upcoming and payment method known and payment status not (Unavailable, Successful, ReceiptUnderVerification).
Usage: gen_gcn46_fixtures.py [--out-dir DIR] [--now 2026-10-12T08:00:00Z] [--selftest]"""
import argparse, datetime as dt, json, os, sys

STATUSES = {"Booked", "Confirmed", "Completed", "Cancelled"}
PAY_STATUS = {"Pending", "AwaitingBankTransferReceipt", "ReceiptUnderVerification", "AwaitingGatewayPayment", "Successful", "Failed"}
PAY_METHOD = {"Cash", "BankTransfer", "PaymentGateway"}
FMT = "%Y-%m-%dT%H:%M:%SZ"

def oracle(status, start, end, method, pstatus, now):
    st = status if status in STATUSES else "Unavailable"
    valid = start is not None and end > start
    if st in ("Completed", "Cancelled"): section = "Previous"
    elif st == "Unavailable" or not valid: section = "Unavailable"
    else: section = "Previous" if end <= now else "Upcoming"
    pm = None if method is None else (method if method in PAY_METHOD else "Unavailable")
    ps = None if pstatus is None else (pstatus if pstatus in PAY_STATUS else "Unavailable")
    can_pay = section == "Upcoming" and pm != "Unavailable" and ps not in ("Unavailable", "Successful", "ReceiptUnderVerification")
    return {"status": st, "section": section, "paymentMethod": pm, "paymentStatus": ps, "canPay": can_pay}

# (days from today 00:00 UTC, stored status, stored method, stored payment status)   offsets are >= 2 days away from 'now' so sections stay stable for ~1.5 days
TEMPLATE_12 = [
    (2, "Booked", None, None), (5, "Confirmed", "Cash", "Pending"), (9, "Booked", "BankTransfer", "AwaitingBankTransferReceipt"),
    (14, "Booked", "BankTransfer", "ReceiptUnderVerification"), (20, "Confirmed", "PaymentGateway", "AwaitingGatewayPayment"),
    (-3, "Completed", "PaymentGateway", "Successful"), (-8, "Completed", "Cash", "Pending"), (-12, "Cancelled", "BankTransfer", "AwaitingBankTransferReceipt"),
    (-30, "Completed", "Cash", "Successful"), (-5, "Booked", "PaymentGateway", "Failed"), (-2, "Confirmed", "Cash", "Pending"), (40, "Booked", "PaymentGateway", "Failed"),
]
# edge-case patient S: (days, status, method, payment status, end-before-start?)
EDGE_14 = [
    (10, "Completed", "Cash", "Pending", False),            # completed in the future -> Previous
    (10, "Cancelled", None, None, False),                   # cancelled in the future -> Previous
    (-2, "Booked", None, None, False),                      # booked but ended -> Previous
    (3, "Booked", None, None, False),                       # upcoming, no payment -> canPay
    (6, "Confirmed", "Cash", "Pending", False),
    (7, "Archived", None, None, False),                     # unknown stored status -> Unavailable
    (7, "Booked", None, None, True),                        # end before start -> Unavailable
    (8, "Booked", "Crypto", "Pending", False),              # unknown stored payment method
    (8, "Booked", "Cash", "Refunded", False),               # unknown stored payment status
    (12, "Booked", "PaymentGateway", "Successful", False),
    (12, "Booked", "BankTransfer", "ReceiptUnderVerification", False),
    (13, "Booked", "BankTransfer", "AwaitingBankTransferReceipt", False),
    (15, "Confirmed", "PaymentGateway", "AwaitingGatewayPayment", False),
    (16, "Booked", "PaymentGateway", "Failed", False),
]
DOCTORS = ["Dr Synthetic One", "Dr Synthetic Two", "Dr Synthetic Three", "Dr Synthetic Four", "Dr Synthetic Five"]

def build(now):
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    patients = {}; rows = []; pays = []
    def add(key, gid, idx, row_id, days, status, method, pstatus, bad_time=False):
        start = day0 + dt.timedelta(days=days, hours=4 + (idx % 6) * 0.5)
        end = start - dt.timedelta(hours=1) if bad_time else start + dt.timedelta(minutes=30)
        exp = oracle(status, start, end, method, pstatus, now)
        ref = f"CN-APT-{key}-{idx:03d}"
        doc_no = idx % 5
        rows.append({"Id": row_id, "AppointmentReference": ref, "PatientId": gid, "DoctorId": f"46d00000-0000-4000-8000-{doc_no + 1:012d}", "DoctorName": DOCTORS[doc_no],
                     "DoctorAvailabilitySlotId": 460000000 + row_id, "AppointmentStartUtc": start, "AppointmentEndUtc": end, "Status": status})
        if method is not None:
            pays.append({"AppointmentId": row_id, "PatientId": gid, "Amount": "2700.00", "Method": method, "Status": pstatus})
        patients[key]["appointments"].append({"id": row_id, "reference": ref, "doctorName": DOCTORS[doc_no], "startUtc": start.strftime(FMT), "endUtc": end.strftime(FMT), **exp})
    def patient(key, n, label):
        patients[key] = {"id": f"46a00000-0000-4000-8000-{n:012d}", "label": label, "appointments": []}
        return patients[key]["id"]
    for n in range(1, 21):
        key = f"L{n:02d}"; gid = patient(key, n, "load patient")
        for i, (d, s, m, p) in enumerate(TEMPLATE_12, 1): add(key, gid, i, n * 1000 + i, d, s, m, p)
    gid = patient("S", 101, "edge-case patient")
    for i, (d, s, m, p, bad) in enumerate(EDGE_14, 1): add("S", gid, i, 30000 + i, d, s, m, p, bad)
    gid = patient("BIG", 102, "large-history patient (200 appointments)")
    for i in range(200):
        d, s, m, p = TEMPLATE_12[i % 12]; c = i // 12; d = d + (13 * c if d > 0 else -13 * c)
        add("BIG", gid, i + 1, 31000 + i + 1, d, s, m, p)
    for key, n in (("A", 103), ("B", 104)):
        gid = patient(key, n, "isolation patient " + key)
        for i, (d, s, m, p) in enumerate(TEMPLATE_12, 1): add(key, gid, i, (32000 if key == "A" else 33000) + i, d, s, m, p)
    return day0, patients, rows, pays

def sql(rows, pays, now):
    q = lambda v: "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"
    ts = lambda d: d.strftime("%Y-%m-%d %H:%M:%S")
    created = ts(now)
    out = ["-- GCN-46 synthetic seed (INSERT only). Generated " + now.strftime(FMT), "START TRANSACTION;"]
    cols = "`Id`, `AppointmentReference`, `PatientId`, `DoctorId`, `DoctorName`, `DoctorAvailabilitySlotId`, `AppointmentStartUtc`, `AppointmentEndUtc`, `Status`, `CreatedAtUtc`, `UpdatedAtUtc`"
    for i in range(0, len(rows), 100):
        vals = ",".join("(" + ",".join([str(r["Id"]), q(r["AppointmentReference"]), q(r["PatientId"]), q(r["DoctorId"]), q(r["DoctorName"]), str(r["DoctorAvailabilitySlotId"]),
                                         q(ts(r["AppointmentStartUtc"])), q(ts(r["AppointmentEndUtc"])), q(r["Status"]), q(created), "NULL"]) + ")" for r in rows[i:i + 100])
        out.append(f"INSERT INTO `Appointments` ({cols}) VALUES {vals};")
    pcols = "`AppointmentId`, `PatientId`, `Amount`, `Method`, `Status`, `CreatedAtUtc`, `UpdatedAtUtc`"
    for i in range(0, len(pays), 100):
        vals = ",".join("(" + ",".join([str(p["AppointmentId"]), q(p["PatientId"]), p["Amount"], q(p["Method"]), q(p["Status"]), q(created), q(created)]) + ")" for p in pays[i:i + 100])
        out.append(f"INSERT INTO `AppointmentPayments` ({pcols}) VALUES {vals};")
    out.append("COMMIT;")
    return "\n".join(out) + "\n"

def selftest():
    now = dt.datetime(2026, 10, 11, 8, 0, 0)
    day = lambda d, m=0: now + dt.timedelta(days=d, minutes=m)
    cases = [  # the developer's xUnit rule table (SectionAndActionsRespectTimeAndStoredStatus and friends)
        (("Booked", day(1), day(1, 30), None, None), ("Upcoming", True)), (("Confirmed", day(-1), day(-1, 30), None, None), ("Previous", False)),
        (("Completed", day(1), day(1, 30), None, None), ("Previous", False)), (("Cancelled", day(1), day(1, 30), None, None), ("Previous", False)),
        (("999", day(1), day(1, 30), None, None), ("Unavailable", False)),
        (("Booked", day(0, -30), day(0), None, None), ("Previous", False)),                    # ends exactly now -> history
        (("Booked", day(0, -10), day(0, 20), None, None), ("Upcoming", True)),                 # in progress -> upcoming
        (("Booked", day(1), day(1, 30), "BankTransfer", "Successful"), ("Upcoming", False)),
        (("Booked", day(1), day(1, 30), "BankTransfer", "ReceiptUnderVerification"), ("Upcoming", False)),
    ]
    for args, (section, can) in cases:
        r = oracle(args[0], args[1], args[2], args[3], args[4], now)
        assert (r["section"], r["canPay"]) == (section, can), (args, r)
    print("oracle self-test: all", len(cases), "documented rule cases agree")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")); ap.add_argument("--now"); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    selftest()
    if a.selftest: sys.exit(0)
    now = dt.datetime.strptime(a.now, FMT) if a.now else dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, microsecond=0)
    day0, patients, rows, pays = build(now)
    assert len({r["Id"] for r in rows}) == len(rows) and len({r["AppointmentReference"] for r in rows}) == len(rows) and len({r["DoctorAvailabilitySlotId"] for r in rows}) == len(rows)
    for r in rows:   # every offset must be far enough from 'now' for the expectation to stay valid for the validity window
        if r["Status"] in STATUSES and r["AppointmentEndUtc"] > r["AppointmentStartUtc"]: assert abs((r["AppointmentStartUtc"] - now).total_seconds()) > 36 * 3600 or r["Status"] in ("Completed", "Cancelled"), r
    os.makedirs(a.out_dir, exist_ok=True)
    fx = {"generatedAtUtc": now.strftime(FMT), "validUntilUtc": (now + dt.timedelta(hours=36)).strftime(FMT), "synthetic": True, "patients": patients}
    json.dump(fx, open(os.path.join(a.out_dir, "fixtures.json"), "w"), indent=1)
    open(os.path.join(a.out_dir, "seed-gcn46.sql"), "w").write(sql(rows, pays, now))
    sec = {}
    for p in patients.values():
        for x in p["appointments"]: sec[x["section"]] = sec.get(x["section"], 0) + 1
    print(f"patients {len(patients)}  appointments {len(rows)}  payments {len(pays)}  sections {sec}  valid until {fx['validUntilUtc']}")
