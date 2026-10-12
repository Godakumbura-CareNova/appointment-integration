#!/usr/bin/env python3
"""GCN-53 six-request suite: SERVER-SIDE REQUEST CHECK from the backend's own request log (no HTTP, no database access). The log lines written after the baseline recorded by the pre-flight must be
EXACTLY six 'Request starting' lines, all GET, in this order, answered with 200, 200, 200, 200, 401, 403: no health check, retry, redirect, setup, teardown, extra or write request.
Writes <out>/evidence/verify-requests.json and exits non-zero on any failed check."""
import datetime as dt, json, os, re, sys
OUT = os.environ.get("GCN53_OUT") or os.path.expanduser("~/carenova/qa-reports/GCN-53/jmeter-six"); EVID = os.path.join(OUT, "evidence"); FMT = "%Y-%m-%dT%H:%M:%SZ"
checks = []
def check(name, ok, detail=""): checks.append({"name": name, "passed": bool(ok), "detail": str(detail)[:300]}); print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok or not detail else f"  [{str(detail)[:200]}]"))
print("GCN-53 SIX-REQUEST SERVER-SIDE CHECK (from the backend's own request log; no HTTP)")
base = int(open(os.path.join(EVID, "log-baseline.txt")).read().strip())
lines = open(os.path.join(OUT, "logs", "backend.log"), errors="replace").read().splitlines()[base:]
starts = [(m.group(1), re.sub(r"^https?://[^/]+", "", m.group(2)).split("?")[0]) for l in lines for m in [re.search(r"Request starting HTTP/\S+ (\w+) (\S+)", l)] if m]
fins = [int(m.group(1)) for l in lines for m in [re.search(r"Request finished HTTP/\S+ \w+ \S+ - (\d{3})", l)] if m]
DA, DP, AL, RP = "/api/admin/dashboard/appointments", "/api/admin/dashboard/appointment-payments", "/api/admin/appointments", "/api/admin/reports/appointment-income"
want = [(DA, 200), (DP, 200), (AL, 200), (RP, 200), (DP, 401), (AL, 403)]
check("the server received exactly 6 requests during the run", len(starts) == 6, f"{len(starts)}: {starts}")
check("they are the six expected requests, all GET, in order: summary, payment summary, list, report, payment summary (no token), list (patient)", starts == [("GET", p) for p, _ in want], starts)
check("and they were answered 200, 200, 200, 200, 401, 403", fins == [st for _, st in want], fins)
os.makedirs(EVID, exist_ok=True); passed = all(c["passed"] for c in checks)
json.dump({"mode": "requests", "passed": passed, "generatedAtUtc": dt.datetime.now(dt.timezone.utc).strftime(FMT), "checks": checks, "requests": starts, "statuses": fins}, open(os.path.join(EVID, "verify-requests.json"), "w"), indent=1)
print(f"requests: {'ALL CHECKS PASSED' if passed else 'FAILED'} ({sum(c['passed'] for c in checks)}/{len(checks)})"); sys.exit(0 if passed else 1)
