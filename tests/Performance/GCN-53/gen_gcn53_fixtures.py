#!/usr/bin/env python3
"""GCN-53 synthetic fixture generator (read-only admin dashboard suite). Produces, deterministically for a given 'now':
     <out-dir>/fixtures.json   what every scenario expects, computed by an INDEPENDENT oracle of the documented backend rules (never by calling the API)
     <out-dir>/seed-gcn53.sql  INSERT-only SQL for the isolated database: Appointments, AppointmentPayments, AppointmentReceipts (nothing else)
All data is synthetic: patients 53a1.../53a2..., doctor names 'Dr Synthetic Admin-A/B', references CN-APT-ADM-NNNNN; no real person, number or credential.
Backend rules mirrored (AdminAppointmentsController, AdminAppointmentReportsController, AppointmentDashboardService):
  list: newest first by (CreatedAtUtc, Id); search = reference or doctor name contains the term; page/pageSize limits (pageSize 1..100, page >= 1); payment joined on (appointment, patient)
  dashboard: total, status counts, 5 newest appointments with payment method/status; today = start inside the Asia/Colombo calendar day of the server's 'now'; upcoming = start after now and Booked/Confirmed
  payments dashboard: counts per status, pending bank transfers (ReceiptUnderVerification WITH a PendingVerification receipt), 5 newest dated successful payments, income today / month (Asia/Colombo)
  report: successful payments confirmed in [from, to) and not after now, grouped by Asia/Colombo date; undated successful payments counted separately
  -> everything that depends on the CURRENT time is recomputed by the plan's assertions at run time from the lists stored here.
Default out-dir: GCN53_OUT_DIR or ~/carenova/qa-reports/GCN-53/jmeter/fixtures.
Usage: gen_gcn53_fixtures.py [--out-dir DIR] [--now 2026-10-12T08:00:00Z] [--selftest]"""
import argparse, datetime as dt, json, os, sys
FMT = "%Y-%m-%dT%H:%M:%SZ"
VALID_HOURS = 72
P = {n: f"53a{n}0000-0000-4000-8000-00000000000{n}" for n in (1, 2, 3, 4)}
ADMIN = "53e10000-0000-4000-8000-000000000001"
COL = dt.timedelta(hours=5, minutes=30)
iso = lambda t: t.strftime(FMT)
def colombo_midnight_utc(d): return dt.datetime(d.year, d.month, d.day) - COL     # the UTC instant at which Asia/Colombo date d starts

def build(now):
    day_today = (now + COL).date(); X = (now - dt.timedelta(days=3) + COL).date(); bound = colombo_midnight_utc(X + dt.timedelta(days=1))
    today_noon = colombo_midnight_utc(day_today) + dt.timedelta(hours=12); today_night = colombo_midnight_utc(day_today) + dt.timedelta(hours=21)
    D = lambda days: now + dt.timedelta(days=days)
    starts = {1: D(-30), 2: D(-25), 3: D(-20), 4: today_noon, 5: today_night, 6: D(3), 7: D(5), 8: D(6), 9: D(9), 10: D(4), 11: D(-10), 12: D(-12), 13: D(12), 14: D(15)}
    status = {1: "Completed", 2: "Completed", 3: "Completed", 4: "Booked", 5: "Confirmed", 6: "Booked", 7: "Booked", 8: "Confirmed", 9: "Booked", 10: "Cancelled", 11: "Completed", 12: "NoShow", 13: "Confirmed", 14: "Booked"}
    # payments: (n, method, status, amount, confirmed instant | None, update hours ago)
    pay = {1: ("BankTransfer", "Successful", "1000.00", bound - dt.timedelta(seconds=1)), 2: ("BankTransfer", "Successful", "2000.00", bound), 3: ("Cash", "Successful", "1500.00", bound + dt.timedelta(hours=2)),
           4: ("PaymentGateway", "Successful", "3000.00", D(-8)), 5: ("Cash", "Successful", "500.00", None), 6: ("PaymentGateway", "Successful", "700.00", D(2)),
           7: ("BankTransfer", "ReceiptUnderVerification", "1800.00", None), 8: ("BankTransfer", "ReceiptUnderVerification", "1900.00", None), 9: ("Cash", "Pending", "1200.00", None),
           10: ("PaymentGateway", "Failed", "900.00", None), 11: ("Cash", "Successful", "2500.00", now - dt.timedelta(hours=1))}
    appts, pays, recs = [], [], []
    for n in range(1, 15):
        aid = 53000 + n; pn = (n - 1) % 4 + 1; s = starts[n].replace(microsecond=0, second=0) if n not in (4, 5) else starts[n]
        appts.append({"id": aid, "appointmentReference": f"CN-APT-ADM-{aid}", "patientId": P[pn], "doctorName": "Dr Synthetic Admin-" + ("A" if n % 2 else "B"), "status": status[n],
                      "startUtc": iso(s), "endUtc": iso(s + dt.timedelta(minutes=30)), "createdAtUtc": iso((now - dt.timedelta(hours=15 - n)).replace(microsecond=0))})
        if n in pay:
            m, st, amount, conf = pay[n]
            pays.append({"id": aid, "appointmentId": aid, "patientId": P[pn], "amount": amount, "method": m, "status": st, "confirmedAtUtc": iso(conf.replace(microsecond=0)) if conf else None,
                         "updatedAtUtc": iso((now - dt.timedelta(hours=n)).replace(microsecond=0)), "reference": f"CN-APT-ADM-{aid}"})
    recs = [{"id": 53007, "paymentId": 53007, "appointmentId": 53007, "patientId": P[(7 - 1) % 4 + 1], "status": "PendingVerification", "uploadedAtUtc": iso(now.replace(microsecond=0))},
            {"id": 53008, "paymentId": 53008, "appointmentId": 53008, "patientId": P[(8 - 1) % 4 + 1], "status": "Rejected", "uploadedAtUtc": iso(now.replace(microsecond=0))}]
    return appts, pays, recs

def expectations(appts, pays, recs, now):
    by = {a["id"]: a for a in appts}; pay_of = {p["appointmentId"]: p for p in pays}
    newest = sorted(appts, key=lambda a: (a["createdAtUtc"], a["id"]), reverse=True)
    row = lambda a: {"id": a["id"], "reference": a["appointmentReference"], "patientId": a["patientId"], "doctorName": a["doctorName"], "startUtc": a["startUtc"], "status": a["status"],
                     "paymentMethod": (pay_of.get(a["id"]) or {}).get("method"), "paymentStatus": (pay_of.get(a["id"]) or {}).get("status")}
    def page(items, number, size, query):
        sl = items[(number - 1) * size: number * size]
        return {"query": query, "status": 200, "ids": [a["id"] for a in sl], "rows": [row(a) for a in sl], "totalCount": len(items), "page": number, "pageSize": size, "totalPages": -(-len(items) // size)}
    queries = {"default": page(newest, 1, 20, "page=1&pageSize=20"), "page2": page(newest, 2, 5, "page=2&pageSize=5"),
               "search": page([a for a in newest if "Admin-B" in a["doctorName"] or "Admin-B" in a["appointmentReference"]], 1, 20, "search=Admin-B&page=1&pageSize=20"),
               "reference": page([a for a in newest if "CN-APT-ADM-5300" in a["appointmentReference"]], 2, 5, "search=CN-APT-ADM-5300&page=2&pageSize=5"),
               "repeat": page(newest, 1, 5, "page=1&pageSize=5")}
    counts = {}
    for a in appts: counts[a["status"]] = counts.get(a["status"], 0) + 1
    recent = newest[:5]
    dash = {"totalAppointments": len(appts), "statusCounts": counts, "recentIds": [a["id"] for a in recent], "recent": [{"id": a["id"], "reference": a["appointmentReference"], "doctorName": a["doctorName"], "startUtc": a["startUtc"],
            "status": a["status"], "paymentMethod": row(a)["paymentMethod"], "paymentStatus": row(a)["paymentStatus"]} for a in recent]}
    pc = {}
    for p in pays: pc[p["status"]] = pc.get(p["status"], 0) + 1
    pend = [p for p in pays if p["method"] == "BankTransfer" and p["status"] == "ReceiptUnderVerification" and any(r["paymentId"] == p["id"] and r["status"] == "PendingVerification" for r in recs)]
    pdash = {"totalPayments": len(pays), "statusCounts": pc, "pendingTotal": len(pend), "pendingIds": [p["id"] for p in sorted(pend, key=lambda p: (p["updatedAtUtc"], p["id"]))[:5]], "payments": pays}
    f = now.replace(microsecond=0)
    report = {"from": iso(dt.datetime(f.year, f.month, f.day) - dt.timedelta(days=20)), "to": iso(dt.datetime(f.year, f.month, f.day) + dt.timedelta(days=1)),
              "badFrom": iso(dt.datetime(f.year, f.month, f.day) - dt.timedelta(days=40)), "badTo": iso(dt.datetime(f.year, f.month, f.day)), "payments": pays}
    return queries, dash, pdash, report

def sql(appts, pays, recs, now):
    q = lambda v: "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"
    ts = lambda s: dt.datetime.strptime(s, FMT).strftime("%Y-%m-%d %H:%M:%S"); created = now.strftime("%Y-%m-%d %H:%M:%S")
    out = ["-- GCN-53 synthetic seed (INSERT only). Generated " + now.strftime(FMT), "START TRANSACTION;"]
    cols = "`Id`, `AppointmentReference`, `PatientId`, `DoctorId`, `DoctorName`, `DoctorAvailabilitySlotId`, `AppointmentStartUtc`, `AppointmentEndUtc`, `Status`, `CreatedAtUtc`, `UpdatedAtUtc`"
    out.append(f"INSERT INTO `Appointments` ({cols}) VALUES " + ",".join("(" + ",".join([str(a["id"]), q(a["appointmentReference"]), q(a["patientId"]), q("53d10000-0000-4000-8000-000000000001"), q(a["doctorName"]), str(530000000 + a["id"]),
               q(ts(a["startUtc"])), q(ts(a["endUtc"])), q(a["status"]), q(ts(a["createdAtUtc"])), "NULL"]) + ")" for a in appts) + ";")
    pc = "`Id`, `AppointmentId`, `PatientId`, `Amount`, `Method`, `Status`, `CreatedAtUtc`, `UpdatedAtUtc`, `ConfirmedAtUtc`"
    out.append(f"INSERT INTO `AppointmentPayments` ({pc}) VALUES " + ",".join("(" + ",".join([str(p["id"]), str(p["appointmentId"]), q(p["patientId"]), p["amount"], q(p["method"]), q(p["status"]), q(created), q(ts(p["updatedAtUtc"])),
               q(ts(p["confirmedAtUtc"]) if p["confirmedAtUtc"] else None)]) + ")" for p in pays) + ";")
    rc = "`Id`, `AppointmentPaymentId`, `AppointmentId`, `PatientId`, `OriginalFileName`, `BlobName`, `ContainerName`, `ContentType`, `SizeBytes`, `Status`, `UploadedAtUtc`, `ReviewedBy`, `ReviewedAtUtc`, `RejectionReason`"
    out.append(f"INSERT INTO `AppointmentReceipts` ({rc}) VALUES " + ",".join("(" + ",".join([str(r["id"]), str(r["paymentId"]), str(r["appointmentId"]), q(r["patientId"]), q("synthetic-receipt.pdf"), q(f"synthetic/none-{r['id']}"),
               q("synthetic"), q("application/pdf"), "1", q(r["status"]), q(ts(r["uploadedAtUtc"])), "NULL", "NULL", q("Synthetic rejection" if r["status"] == "Rejected" else None)]) + ")" for r in recs) + ";")
    out.append("COMMIT;"); return "\n".join(out) + "\n"

def selftest():
    now = dt.datetime(2026, 10, 12, 8, 0, 0); appts, pays, recs = build(now); q, dash, pdash, report = expectations(appts, pays, recs, now)
    assert len(appts) == 14 and len(pays) == 11 and len(recs) == 2
    assert q["default"]["ids"] == list(range(53014, 53000, -1)) and q["default"]["totalPages"] == 1
    assert q["page2"]["ids"] == [53009, 53008, 53007, 53006, 53005] and q["page2"]["totalPages"] == 3 and q["page2"]["totalCount"] == 14
    assert q["search"]["ids"] == [53014, 53012, 53010, 53008, 53006, 53004, 53002] and q["search"]["totalCount"] == 7
    assert q["reference"]["totalCount"] == 9 and len(q["reference"]["ids"]) == 4 and q["reference"]["ids"][0] == 53004 and q["reference"]["totalPages"] == 2, q["reference"]
    assert dash["recentIds"] == [53014, 53013, 53012, 53011, 53010] and dash["statusCounts"] == {"Completed": 4, "Booked": 5, "Confirmed": 3, "Cancelled": 1, "NoShow": 1}
    assert dash["recent"][4]["paymentStatus"] == "Failed" and dash["recent"][0]["paymentMethod"] is None
    assert pdash["statusCounts"] == {"Successful": 7, "ReceiptUnderVerification": 2, "Pending": 1, "Failed": 1} and pdash["pendingIds"] == [53007] and pdash["pendingTotal"] == 1
    p1, p2 = [p for p in pays if p["id"] in (53001, 53002)]
    # the two confirmations either side of the Asia/Colombo midnight fall on different Sri Lanka dates
    d = lambda p: (dt.datetime.strptime(p["confirmedAtUtc"], FMT) + COL).date()
    assert d(p1) != d(p2) and (d(p2) - d(p1)).days == 1
    assert report["from"] < report["to"] and (dt.datetime.strptime(report["to"], FMT) - dt.datetime.strptime(report["from"], FMT)).days == 21 and (dt.datetime.strptime(report["badTo"], FMT) - dt.datetime.strptime(report["badFrom"], FMT)).days == 40
    s = sql(appts, pays, recs, now); assert s.count("INSERT INTO") == 3 and not any(l.upper().startswith(("UPDATE ", "DELETE ", "DROP ", "ALTER ", "TRUNCATE ")) for l in s.splitlines())
    print("fixture self-test: list pages, dashboard counts, pending transfers and the Sri Lanka date boundary agree with the documented rules")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out-dir", default=os.path.join(os.environ.get("GCN53_OUT_DIR") or os.path.expanduser("~/carenova/qa-reports/GCN-53/jmeter"), "fixtures")); ap.add_argument("--now"); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(); selftest()
    if a.selftest: sys.exit(0)
    now = dt.datetime.strptime(a.now, FMT) if a.now else dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, microsecond=0)
    appts, pays, recs = build(now); queries, dash, pdash, report = expectations(appts, pays, recs, now); os.makedirs(a.out_dir, exist_ok=True)
    fx = {"generatedAtUtc": iso(now), "validUntilUtc": iso(now + dt.timedelta(hours=VALID_HOURS)), "synthetic": True, "counts": {"appointments": len(appts), "payments": len(pays), "receipts": len(recs)},
          "actors": {"admin": ADMIN, "patient": P[1], "doctor": "53d10000-0000-4000-8000-000000000001", "staff": "53c10000-0000-4000-8000-000000000001"}, "appointments": appts,
          "queries": queries, "dashboard": dash, "payments": pdash, "report": report}
    json.dump(fx, open(os.path.join(a.out_dir, "fixtures.json"), "w"), indent=1)
    open(os.path.join(a.out_dir, "seed-gcn53.sql"), "w").write(sql(appts, pays, recs, now))
    print(f"appointments {len(appts)}  payments {len(pays)}  receipts {len(recs)}  valid until {fx['validUntilUtc']}")
