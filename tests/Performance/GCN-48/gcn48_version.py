#!/usr/bin/env python3
"""GCN-48 offline port of the backend's cancellation decision and of the confirmation version, used to compute JM-05's expectedVersion BEFORE any request is sent.
Ports (AppointmentCancellationPolicy.Evaluate and AppointmentCancellationService.Version):
    version = HEX(SHA256(UTF8(System.Text.Json(new { snapshot, decision }))))   with default serializer options (PascalCase names, declaration order).
Every serialisation rule that matters is reproduced explicitly: DateTime of kind Unspecified -> yyyy-MM-ddTHH:mm:ss[.fffffff trimmed]; decimals keep their scale (1500.00); Guid lower-case.
This port is NOT trusted on its own: gcn48-check-version.sh feeds the same snapshots to the REAL backend code (published build) through VersionOracle and compares every version."""
import datetime as dt, hashlib
from decimal import Decimal

SAFE = set(chr(c) for c in range(32, 127)) - set('"&\'+<>\\`')      # JavaScriptEncoder.Default escapes quote, & \' + < > backslash, backtick and everything non-ASCII
def jstr(s):
    if s is None: return "null"
    bad = [c for c in s if c not in SAFE]
    if bad: raise ValueError("character(s) %r would be escaped by System.Text.Json; extend the port before using this text" % bad)
    return '"' + s + '"'
def jdt(d):
    if d is None: return "null"
    s = d.strftime("%Y-%m-%dT%H:%M:%S"); frac = ("%06d" % d.microsecond + "0").rstrip("0")     # .NET writes 7 digits and trims trailing zeros
    return '"' + s + ("." + frac if frac else "") + '"'
def jdec(x): return "0" if x is None else str(x)
def jbool(b): return "true" if b else "false"
def jint(i): return "null" if i is None else str(int(i))

def evaluate(s, now):
    """Returns the decision as a dict; RefundAmount is kept as the exact decimal text .NET would write."""
    def deny(code, msg): return dict(Allowed=False, ReasonCode=code, Message=msg, RefundOutcome="NotRequired", RefundAmount="0", Ack=False)
    def allow(code, msg, outcome="NotRequired", refund="0", ack=False): return dict(Allowed=True, ReasonCode=code, Message=msg, RefundOutcome=outcome, RefundAmount=refund, Ack=ack)
    method, status = s["PaymentMethod"], s["PaymentStatus"]
    if s["Status"] not in ("Booked", "Confirmed"): return deny("AppointmentNotEligible", "This appointment cannot be cancelled in its current status.")
    if s["StartUtc"] == dt.datetime.min or s["EndUtc"] <= s["StartUtc"]: return deny("InformationUnavailable", "Appointment time is unavailable. Refresh or contact the pharmacy.")
    if now >= s["StartUtc"]: return deny("AppointmentStarted", "Appointments cannot be cancelled once their scheduled start time has been reached.")
    if s["HasPendingCheckout"]: return deny("CheckoutInProgress", "An online checkout is still in progress. Wait for its outcome before cancelling.")
    if s["HasSuccessfulCheckout"] and (method != "PaymentGateway" or status != "Successful"):
        return deny("PaymentNeedsReview", "A successful online payment is recorded. Cancellation is unavailable; contact the pharmacy to review payment information.")
    if s["PaymentId"] is None:
        return allow("Unpaid", "No refund is required because payment has not been made.") if method is None and status is None else deny("InformationUnavailable", "Payment information is inconsistent. Refresh or contact the pharmacy.")
    if s["Amount"] <= 0: return deny("InformationUnavailable", "Payment information is unavailable. Refresh or contact the pharmacy.")
    if method == "Cash" and status == "Successful": return deny("CashAlreadyPaid", "A cash appointment that has already been paid cannot be cancelled here.")
    if method == "Cash" and status == "Pending": return allow("Unpaid", "No refund is required because cash payment has not been made.")
    if method == "BankTransfer" and status == "ReceiptUnderVerification": return deny("ReceiptUnderVerification", "Your bank transfer receipt is being verified. Cancellation is available after verification is resolved.")
    if method == "BankTransfer" and status in ("AwaitingBankTransferReceipt", "Pending", "Failed"): return allow("Unpaid", "No verified payment has been recorded, so no refund is required.")
    if method == "BankTransfer" and status == "Successful":
        if s["StartUtc"] - now >= dt.timedelta(hours=6):
            return allow("RefundEligible", "Eligible for a refund, awaiting manual processing by pharmacy staff.", "Eligible", str(s["Amount"]))
        return allow("RefundNotEligible", "Less than 6 hours remain. You may cancel, but no refund is available.", "NotEligible", "0", True)
    if method == "PaymentGateway" and status == "Successful": return deny("GatewayAlreadyPaid", "Patient cancellation and refunds are not available after successful online payment.")
    if method == "PaymentGateway" and status in ("AwaitingGatewayPayment", "Failed"): return allow("Unpaid", "No successful online payment is recorded. No refund is required.")
    return deny("InformationUnavailable", "Payment information is unavailable or inconsistent. Refresh or contact the pharmacy.")

def snapshot_json(s):
    return ('{"AppointmentId":%d,"PatientId":"%s","Status":%s,"StartUtc":%s,"EndUtc":%s,"UpdatedAtUtc":%s,"PaymentId":%s,"PaymentMethod":%s,"PaymentStatus":%s,"Amount":%s,'
            '"PaymentUpdatedAtUtc":%s,"HasPendingCheckout":%s,"AttemptsVersion":%s,"HasSuccessfulCheckout":%s}') % (
        s["AppointmentId"], str(s["PatientId"]).lower(), jstr(s["Status"]), jdt(s["StartUtc"]), jdt(s["EndUtc"]), jdt(s["UpdatedAtUtc"]), jint(s["PaymentId"]),
        jstr(s["PaymentMethod"]), jstr(s["PaymentStatus"]), jdec(s["Amount"]), jdt(s["PaymentUpdatedAtUtc"]), jbool(s["HasPendingCheckout"]), jstr(s["AttemptsVersion"]), jbool(s["HasSuccessfulCheckout"]))
def decision_json(d):
    return '{"Allowed":%s,"ReasonCode":%s,"Message":%s,"RefundOutcome":%s,"RefundAmount":%s,"RequiresNoRefundAcknowledgement":%s}' % (
        jbool(d["Allowed"]), jstr(d["ReasonCode"]), jstr(d["Message"]), jstr(d["RefundOutcome"]), d["RefundAmount"], jbool(d["Ack"]))
def version(s, d):
    return hashlib.sha256(('{"snapshot":%s,"decision":%s}' % (snapshot_json(s), decision_json(d))).encode("utf-8")).hexdigest().upper()

def snapshot(**k):
    base = dict(AppointmentId=0, PatientId="", Status="Booked", StartUtc=None, EndUtc=None, UpdatedAtUtc=None, PaymentId=None, PaymentMethod=None, PaymentStatus=None, Amount=Decimal("0"),
                PaymentUpdatedAtUtc=None, HasPendingCheckout=False, AttemptsVersion="[]", HasSuccessfulCheckout=False)
    base.update(k); return base

def vector(s, now):
    """The same snapshot as plain JSON for the .NET oracle (timestamps as MySQL text, decimals as text so that the scale is kept)."""
    f = lambda d: None if d is None else d.strftime("%Y-%m-%d %H:%M:%S.%f")
    return {"appointmentId": s["AppointmentId"], "patientId": str(s["PatientId"]).lower(), "status": s["Status"], "startUtc": f(s["StartUtc"]), "endUtc": f(s["EndUtc"]), "updatedAtUtc": f(s["UpdatedAtUtc"]),
            "paymentId": s["PaymentId"], "method": s["PaymentMethod"], "paymentStatus": s["PaymentStatus"], "amount": str(s["Amount"]), "paymentUpdatedAtUtc": f(s["PaymentUpdatedAtUtc"]),
            "hasPendingCheckout": s["HasPendingCheckout"], "attemptsVersion": s["AttemptsVersion"], "hasSuccessfulCheckout": s["HasSuccessfulCheckout"], "nowUtc": f(now)}

def matrix(now):
    """A broad set of snapshots (every payment combination, boundaries, odd states) for the oracle comparison."""
    out = []; D = dt.timedelta; n = 0
    pay = [(None, None), ("Cash", "Pending"), ("Cash", "Successful"), ("Cash", "Unknown"), ("BankTransfer", "AwaitingBankTransferReceipt"), ("BankTransfer", "Pending"), ("BankTransfer", "Failed"),
           ("BankTransfer", "ReceiptUnderVerification"), ("BankTransfer", "Successful"), ("PaymentGateway", "Successful"), ("PaymentGateway", "Failed"), ("PaymentGateway", "AwaitingGatewayPayment"), ("Unavailable", "Successful")]
    for hours in (72, 6.0, 5.999999, 2, 0, -1):
        for status in ("Booked", "Confirmed", "Completed"):
            for m, p in pay:
                n += 1; start = now + D(hours=hours)
                has_pay = m is not None or p is not None
                out.append(snapshot(AppointmentId=48000 + n, PatientId="48a10000-0000-4000-8000-000000000001", Status=status, StartUtc=start, EndUtc=start + D(minutes=30),
                                    PaymentId=(48000 + n) if has_pay else None, PaymentMethod=m, PaymentStatus=p, Amount=Decimal("1500.00") if has_pay else Decimal("0"),
                                    PaymentUpdatedAtUtc=now if has_pay else None))
    base = out[0]
    out.append({**base, "AppointmentId": 49001, "Amount": Decimal("2000.50"), "PaymentMethod": "BankTransfer", "PaymentStatus": "Successful", "PaymentId": 49001, "PaymentUpdatedAtUtc": now + D(microseconds=123456), "UpdatedAtUtc": now + D(seconds=5, microseconds=700000)})
    out.append({**base, "AppointmentId": 49002, "HasPendingCheckout": True, "PaymentMethod": "Cash", "PaymentStatus": "Pending", "PaymentId": 49002, "Amount": Decimal("1500.00"), "PaymentUpdatedAtUtc": now})
    out.append({**base, "AppointmentId": 49003, "HasSuccessfulCheckout": True, "PaymentMethod": "BankTransfer", "PaymentStatus": "Successful", "PaymentId": 49003, "Amount": Decimal("1500.00"), "PaymentUpdatedAtUtc": now})
    out.append({**base, "AppointmentId": 49004, "StartUtc": dt.datetime.min, "EndUtc": dt.datetime.min})
    out.append({**base, "AppointmentId": 49005, "PaymentId": 49005, "PaymentMethod": "Cash", "PaymentStatus": "Pending", "Amount": Decimal("0.00"), "PaymentUpdatedAtUtc": now})
    return out

def selftest():
    now = dt.datetime(2026, 10, 12, 8, 0, 0)
    d = evaluate(snapshot(AppointmentId=1, PatientId="x", StartUtc=now + dt.timedelta(hours=72), EndUtc=now + dt.timedelta(hours=72, minutes=30), PaymentId=1, PaymentMethod="BankTransfer", PaymentStatus="Successful", Amount=Decimal("1500.00"), PaymentUpdatedAtUtc=now), now)
    assert d["ReasonCode"] == "RefundEligible" and d["RefundAmount"] == "1500.00" and d["Allowed"]
    assert jdt(dt.datetime(2026, 1, 2, 3, 4, 5)) == '"2026-01-02T03:04:05"' and jdt(dt.datetime(2026, 1, 2, 3, 4, 5, 120000)) == '"2026-01-02T03:04:05.12"'
    assert jdt(dt.datetime(2026, 1, 2, 3, 4, 5, 123456)) == '"2026-01-02T03:04:05.123456"'
    try: jstr("it's"); raise SystemExit("jstr must refuse text System.Text.Json would escape")
    except ValueError: pass
    assert len(matrix(now)) == 6 * 3 * 13 + 5
    print("version port self-test: formatting rules and the refund-eligible decision as documented")
if __name__ == "__main__": selftest()
