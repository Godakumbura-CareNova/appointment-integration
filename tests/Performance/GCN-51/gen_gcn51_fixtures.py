#!/usr/bin/env python3
"""GCN-51 synthetic fixture generator (read-only dashboard suite). Produces, deterministically for a given 'now':
     fixtures/fixtures.json    what every scenario expects, computed by an INDEPENDENT oracle of the documented backend rules (never by calling the API)
     fixtures/seed-gcn51.sql   INSERT-only SQL for the isolated database: Appointments, AppointmentPayments, AppointmentReceipts (no cancellation, refund, reconciliation or audit rows)
All data is synthetic: patients 51a1.../51a2.../51a3.../51a4..., doctors 51d1.../51d2..., staff 51c1..., references CN-APT-DSH-NNNNN; no real person, number or credential.
Backend rules mirrored:
  patient dashboard (AppointmentDashboardService.GetPatientAsync): upcoming = the patient's appointments that are Booked/Confirmed and start after now; count of all of them, the first 5 by (start, id);
      payment status counts = ALL the patient's payments grouped by status; payment of a listed appointment = its payment row (method, status) or null
  staff payments (GetStaffPaymentsAsync): pending transfers = BankTransfer + ReceiptUnderVerification payments that have a PendingVerification receipt (count + first 5 by UpdatedAtUtc, id);
      income = Successful payments without a reconciliation row: dated (ConfirmedAtUtc set and <= now), today / month in Asia/Colombo, undated count and amount; recent = 5 newest dated by (confirmed desc, id desc)
      -> the income figures depend on the CURRENT time; the plan's assertion recomputes them from the payment list at run time (oracle in Groovy), this file stores the payment list
  doctor appointments (DoctorAppointmentService, GCN-47): Sri Lanka calendar day = UTC + 5.5 h; every fixture start is at least 9 days from now so no flag depends on the time of day
Usage: gen_gcn51_fixtures.py [--out-dir DIR] [--now 2026-10-12T08:00:00Z] [--selftest]"""
import argparse, datetime as dt, json, os, sys
FMT = "%Y-%m-%dT%H:%M:%SZ"
VALID_HOURS = 72
P = {n: f"51a{n}0000-0000-4000-8000-00000000000{n}" for n in (1, 2, 3, 4)}
D1, D2 = "51d10000-0000-4000-8000-000000000001", "51d20000-0000-4000-8000-000000000002"
STAFF = "51c10000-0000-4000-8000-000000000001"

# (id, patient, doctor, start offset in HOURS from now, stored status, method, payment status, amount, confirmed offset hours | None | "NULL", payment updated offset hours, receipt status | None)
H = lambda days, hour=0: days * 24 + hour
ROWS = [
    (51001, 1, D1, H(10), "Booked", "Cash", "Pending", "1500.00", None, -1, None),
    (51002, 1, D1, H(11), "Confirmed", "BankTransfer", "Successful", "2500.00", -0.5, -2, None),
    (51003, 1, D1, H(12), "Booked", "BankTransfer", "ReceiptUnderVerification", "1800.00", None, -3, "PendingVerification"),
    (51004, 1, D1, H(13), "Confirmed", "PaymentGateway", "Successful", "3000.00", -26, -4, None),
    (51005, 1, D1, H(14), "Booked", None, None, None, None, None, None),
    (51006, 1, D1, H(15), "Booked", "BankTransfer", "AwaitingBankTransferReceipt", "2000.00", None, -5, None),
    (51007, 1, D1, H(16), "Confirmed", "Cash", "Successful", "1200.00", "NULL", -6, None),
    (51008, 1, D1, H(12, 2), "Cancelled", "Cash", "Failed", "900.00", None, -7, None),
    (51009, 1, D1, -H(10), "Completed", "Cash", "Successful", "1500.00", -H(10), -H(10), None),
    (51010, 1, D1, -H(10, 2), "Booked", None, None, None, None, None, None),
    (51101, 2, D1, H(11, 2), "Booked", "BankTransfer", "ReceiptUnderVerification", "1500.00", None, -8, "PendingVerification"),
    (51102, 2, D1, -H(9), "Completed", "BankTransfer", "Successful", "2200.00", -H(40), -H(40), None),
    (51103, 3, D1, H(13, 2), "Confirmed", "Cash", "Pending", "1500.00", None, -9, None),
    (51104, 4, D1, -H(12), "Completed", None, None, None, None, None, None),
    (51105, 2, D1, H(17), "Booked", "BankTransfer", "ReceiptUnderVerification", "1500.00", None, -10, "PendingVerification"),
    (51106, 3, D1, H(18), "Booked", "BankTransfer", "ReceiptUnderVerification", "1500.00", None, -11, "PendingVerification"),
    (51107, 4, D1, H(19), "Booked", "BankTransfer", "ReceiptUnderVerification", "1500.00", None, -12, "PendingVerification"),
    (51108, 4, D1, H(20), "Booked", "BankTransfer", "ReceiptUnderVerification", "1500.00", None, -13, "PendingVerification"),
    (51109, 4, D1, H(21), "Booked", "BankTransfer", "ReceiptUnderVerification", "1500.00", None, -14, "Rejected"),       # excluded: no PENDING receipt
    (51110, 3, D1, H(14, 2), "Confirmed", "BankTransfer", "Successful", "1700.00", H(2), -15, None),                       # confirmed in the FUTURE: counts nowhere
    (51111, 3, D1, -H(15), "Completed", "BankTransfer", "Successful", "2600.00", -H(3), -H(3), None),
    (51112, 4, D1, -H(25), "Completed", "BankTransfer", "Successful", "1100.00", -H(50), -H(50), None),
    (51201, 4, D2, H(10, 3), "Booked", None, None, None, None, None, None),                                               # another doctor's: never in doctor 1's response
]
def sl_date(t): return (t + dt.timedelta(hours=5.5)).date()
def doctor_expect(status, start, end, now):
    valid = end > start; today = sl_date(now); date = sl_date(start)
    comp = status == "Completed"
    allowed = []
    if valid and status in ("Booked", "Confirmed"):
        if status == "Booked": allowed.append("Confirmed")
        if now >= start: allowed.append("Completed")
        if now >= end: allowed.append("NoShow")
    return {"isToday": valid and date == today, "isUpcoming": valid and date > today and status in ("Booked", "Confirmed"), "isCompleted": comp,
            "isHistory": status in ("NoShow", "Cancelled") or (not comp and (not valid or date < today or end <= now)), "allowedStatuses": allowed}

def build(now):
    appts, pays, recs = [], [], []
    iso = lambda t: t.strftime(FMT)
    for rid, pn, doc, hrs, status, method, pstatus, amount, conf, upd, rstatus in ROWS:
        start = (now + dt.timedelta(hours=hrs)).replace(minute=0, second=0, microsecond=0); end = start + dt.timedelta(minutes=30)
        ex = doctor_expect(status, start, end, now)
        appts.append({"id": rid, "appointmentReference": f"CN-APT-DSH-{rid:05d}", "patientId": P[pn], "doctorId": doc, "doctorName": "Dr Synthetic Board" if doc == D1 else "Dr Synthetic Other",
                      "status": status, "startUtc": iso(start), "endUtc": iso(end), "paymentMethod": method, "paymentStatus": pstatus, "doctorExpect": ex})
        if method is not None:
            updated = (now + dt.timedelta(hours=upd)).replace(microsecond=0)
            confirmed = None if conf in (None, "NULL") else (now + dt.timedelta(hours=conf)).replace(microsecond=0)
            pays.append({"id": rid, "appointmentId": rid, "patientId": P[pn], "amount": amount, "method": method, "status": pstatus, "confirmedAtUtc": confirmed and iso(confirmed), "updatedAtUtc": iso(updated), "reference": f"CN-APT-DSH-{rid:05d}"})
            if rstatus: recs.append({"id": rid, "paymentId": rid, "appointmentId": rid, "patientId": P[pn], "status": rstatus, "uploadedAtUtc": iso(updated)})
    return appts, pays, recs

def expectations(appts, pays, recs, now):
    by_id = {a["id"]: a for a in appts}; pay_of = {p["appointmentId"]: p for p in pays}
    # patient 1
    mine = [a for a in appts if a["patientId"] == P[1] and a["status"] in ("Booked", "Confirmed") and dt.datetime.strptime(a["startUtc"], FMT) > now]
    mine.sort(key=lambda a: (a["startUtc"], a["id"]))
    counts = {}
    for p in pays:
        if p["patientId"] == P[1]: counts[p["status"]] = counts.get(p["status"], 0) + 1
    patient = {"upcomingCount": len(mine), "appointments": [{"id": a["id"], "reference": a["appointmentReference"], "doctorName": a["doctorName"], "startUtc": a["startUtc"], "status": a["status"],
               "paymentMethod": (pay_of.get(a["id"]) or {}).get("method"), "paymentStatus": (pay_of.get(a["id"]) or {}).get("status")} for a in mine[:5]], "paymentStatusCounts": counts,
               "foreignReferences": [a["appointmentReference"] for a in appts if a["patientId"] != P[1]]}
    # staff (pending lists are time independent; income is recomputed at run time from 'payments')
    pend = [p for p in pays if p["method"] == "BankTransfer" and p["status"] == "ReceiptUnderVerification" and any(r["paymentId"] == p["id"] and r["status"] == "PendingVerification" for r in recs)]
    pend.sort(key=lambda p: (p["updatedAtUtc"], p["id"]))
    dated = [p for p in pays if p["status"] == "Successful" and p["confirmedAtUtc"] and dt.datetime.strptime(p["confirmedAtUtc"], FMT) <= now]
    dated.sort(key=lambda p: (p["confirmedAtUtc"], p["id"]), reverse=True)
    staff = {"pendingTotal": len(pend), "pendingIds": [p["id"] for p in pend[:5]], "recentIds": [p["id"] for p in dated[:5]], "payments": pays}
    d1 = sorted([a for a in appts if a["doctorId"] == D1], key=lambda a: (a["startUtc"], a["id"]))
    doctor = {"ids": [a["id"] for a in d1], "statistics": {"today": sum(a["doctorExpect"]["isToday"] for a in d1), "upcoming": sum(a["doctorExpect"]["isUpcoming"] for a in d1),
              "completed": sum(a["doctorExpect"]["isCompleted"] for a in d1), "patientCount": len({a["patientId"] for a in d1})}, "appointments": d1, "foreignIds": [a["id"] for a in appts if a["doctorId"] != D1]}
    return patient, staff, doctor

def sql(appts, pays, recs, now):
    q = lambda v: "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"
    ts = lambda s: dt.datetime.strptime(s, FMT).strftime("%Y-%m-%d %H:%M:%S"); created = now.strftime("%Y-%m-%d %H:%M:%S")
    out = ["-- GCN-51 synthetic seed (INSERT only). Generated " + now.strftime(FMT), "START TRANSACTION;"]
    cols = "`Id`, `AppointmentReference`, `PatientId`, `DoctorId`, `DoctorName`, `DoctorAvailabilitySlotId`, `AppointmentStartUtc`, `AppointmentEndUtc`, `Status`, `CreatedAtUtc`, `UpdatedAtUtc`"
    out.append(f"INSERT INTO `Appointments` ({cols}) VALUES " + ",".join("(" + ",".join([str(a["id"]), q(a["appointmentReference"]), q(a["patientId"]), q(a["doctorId"]), q(a["doctorName"]), str(510000000 + a["id"]),
               q(ts(a["startUtc"])), q(ts(a["endUtc"])), q(a["status"]), q(created), "NULL"]) + ")" for a in appts) + ";")
    pc = "`Id`, `AppointmentId`, `PatientId`, `Amount`, `Method`, `Status`, `CreatedAtUtc`, `UpdatedAtUtc`, `ConfirmedAtUtc`"
    out.append(f"INSERT INTO `AppointmentPayments` ({pc}) VALUES " + ",".join("(" + ",".join([str(p["id"]), str(p["appointmentId"]), q(p["patientId"]), p["amount"], q(p["method"]), q(p["status"]), q(created), q(ts(p["updatedAtUtc"])),
               q(ts(p["confirmedAtUtc"]) if p["confirmedAtUtc"] else None)]) + ")" for p in pays) + ";")
    rc = "`Id`, `AppointmentPaymentId`, `AppointmentId`, `PatientId`, `OriginalFileName`, `BlobName`, `ContainerName`, `ContentType`, `SizeBytes`, `Status`, `UploadedAtUtc`, `ReviewedBy`, `ReviewedAtUtc`, `RejectionReason`"
    out.append(f"INSERT INTO `AppointmentReceipts` ({rc}) VALUES " + ",".join("(" + ",".join([str(r["id"]), str(r["paymentId"]), str(r["appointmentId"]), q(r["patientId"]), q("synthetic-receipt.pdf"), q(f"synthetic/none-{r['id']}"),
               q("synthetic"), q("application/pdf"), "1", q(r["status"]), q(ts(r["uploadedAtUtc"])), "NULL", "NULL", q("Synthetic rejection" if r["status"] == "Rejected" else None)]) + ")" for r in recs) + ";")
    out.append("COMMIT;"); return "\n".join(out) + "\n"

def selftest():
    now = dt.datetime(2026, 10, 12, 8, 0, 0); appts, pays, recs = build(now); patient, staff, doctor = expectations(appts, pays, recs, now)
    assert patient["upcomingCount"] == 7 and [a["id"] for a in patient["appointments"]] == [51001, 51002, 51003, 51004, 51005], patient
    assert patient["appointments"][4]["paymentMethod"] is None and patient["appointments"][1]["paymentStatus"] == "Successful"
    assert patient["paymentStatusCounts"] == {"Pending": 1, "Successful": 4, "ReceiptUnderVerification": 1, "AwaitingBankTransferReceipt": 1, "Failed": 1}, patient["paymentStatusCounts"]
    assert staff["pendingTotal"] == 6 and len(staff["pendingIds"]) == 5 and 51109 not in staff["pendingIds"] and staff["pendingIds"][0] == 51108, staff   # oldest update first
    assert staff["recentIds"] == [51002, 51004, 51111, 51009, 51102], staff["recentIds"] and 51110 not in staff["recentIds"]
    assert doctor["statistics"]["today"] == 0 and 51201 not in doctor["ids"] and doctor["statistics"]["completed"] == 5 and doctor["statistics"]["patientCount"] == 4, doctor["statistics"]
    assert all(abs((dt.datetime.strptime(a["startUtc"], FMT) - now).total_seconds()) > 9 * 86400 - 3 * 3600 for a in appts), "every start is at least about 9 days away"
    s = sql(appts, pays, recs, now); assert s.count("INSERT INTO") == 3 and "UPDATE " not in s.replace("UpdatedAtUtc", "")
    print("fixture self-test: patient, staff and doctor expectations agree with the documented rules")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")); ap.add_argument("--now"); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(); selftest()
    if a.selftest: sys.exit(0)
    now = dt.datetime.strptime(a.now, FMT) if a.now else dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, microsecond=0)
    appts, pays, recs = build(now); patient, staff, doctor = expectations(appts, pays, recs, now); os.makedirs(a.out_dir, exist_ok=True)
    fx = {"generatedAtUtc": now.strftime(FMT), "validUntilUtc": (now + dt.timedelta(hours=VALID_HOURS)).strftime(FMT), "synthetic": True, "counts": {"appointments": len(appts), "payments": len(pays), "receipts": len(recs)},
          "actors": {"patient1": P[1], "doctor1": D1, "staff": STAFF}, "appointments": appts, "patient": patient, "staff": staff, "doctor": doctor}
    json.dump(fx, open(os.path.join(a.out_dir, "fixtures.json"), "w"), indent=1)
    open(os.path.join(a.out_dir, "seed-gcn51.sql"), "w").write(sql(appts, pays, recs, now))
    print(f"appointments {len(appts)}  payments {len(pays)}  receipts {len(recs)}  patient upcoming {patient['upcomingCount']}  pending transfers {staff['pendingTotal']}  valid until {fx['validUntilUtc']}")
