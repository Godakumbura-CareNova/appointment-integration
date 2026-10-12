#!/usr/bin/env python3
"""GCN-48 offline verification of the confirmation versions (JM-05's expectedVersion in particular). NO HTTP request, NO database write.
  gcn48_check_version.py --api-dir DIR [--fixtures-dir DIR] [--db]
    1. builds oracle/VersionOracle in a temporary folder outside every repository against the PUBLISHED backend build in DIR (the real policy and Version code);
    2. compares the real code's decision and version with this suite's port (gcn48_version.py) for a broad matrix of snapshots (every payment combination, the 6-hour boundary, odd states);
    3. compares the real code's version with the versions stored in fixtures.json for all eight seeded appointments, JM-05's included;
    4. with --db (after seeding, before the run): asks the REAL service to read the seeded rows from the isolated database (SELECT only) and compares its versions with fixtures.json.
Exit 0 only if every comparison is identical. The versions themselves are never printed."""
import argparse, datetime as dt, json, os, shutil, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import gcn48_version as V
DB, USER, HOST, PORT = "carenova_appointment_gcn48_qa", "gcn48_qa", "127.0.0.1", "3306"
ap = argparse.ArgumentParser(); ap.add_argument("--api-dir", required=True); ap.add_argument("--fixtures-dir", default=os.path.join(HERE, "fixtures")); ap.add_argument("--db", action="store_true"); a = ap.parse_args()
api = os.path.abspath(a.api_dir)
if not os.path.exists(os.path.join(api, "AppointmentIntegration.Api.dll")): sys.exit("no published backend build in " + api)
checks = []
def check(name, ok, detail=""): checks.append({"name": name, "passed": bool(ok), "detail": str(detail)[:300]}); print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok or not detail else f"  [{str(detail)[:200]}]"))

work = tempfile.mkdtemp(prefix="gcn48-oracle-")
try:
    shutil.copy(os.path.join(HERE, "oracle", "VersionOracle.csproj.txt"), os.path.join(work, "VersionOracle.csproj")); shutil.copy(os.path.join(HERE, "oracle", "Program.cs.txt"), os.path.join(work, "Program.cs"))
    b = subprocess.run(["dotnet", "build", "-c", "Release", "--nologo", "-v", "q", f"-p:ApiDir={api}"], cwd=work, capture_output=True, text=True)
    check("the oracle builds against the published backend build (real policy and Version code)", b.returncode == 0, (b.stdout + b.stderr)[-300:])
    if b.returncode == 0:
        # run the oracle with the BACKEND's own dependency set (the published build needs newer System.Text.Json than the shared runtime): a private copy of the build plus the oracle dll
        runner = os.path.join(work, "run"); shutil.copytree(api, runner, symlinks=True)
        shutil.copy(os.path.join(work, "bin", "Release", "net8.0", "VersionOracle.dll"), runner)
        shutil.copy(os.path.join(api, "AppointmentIntegration.Api.runtimeconfig.json"), os.path.join(runner, "VersionOracle.runtimeconfig.json"))
        shutil.copy(os.path.join(api, "AppointmentIntegration.Api.deps.json"), os.path.join(runner, "VersionOracle.deps.json"))
        dll = os.path.join(runner, "VersionOracle.dll")
        def run(args, stdin=None, env=None):
            r = subprocess.run(["dotnet", dll] + args, input=stdin, capture_output=True, text=True, env=env, cwd=work)
            if r.returncode: sys.exit("oracle failed: " + r.stderr.strip()[:300])
            return json.loads(r.stdout)
        now = dt.datetime(2026, 10, 12, 8, 0, 0); snaps = V.matrix(now)
        real = run(["vectors"], json.dumps([V.vector(s, now) for s in snaps]))
        diffs = []
        for s, r in zip(snaps, real):
            d = V.evaluate(s, now)
            mine = (V.version(s, d), d["Allowed"], d["ReasonCode"], d["RefundOutcome"], float(d["RefundAmount"]), d["Ack"])
            if mine != (r["version"], r["allowed"], r["reasonCode"], r["refundOutcome"], float(r["refundAmount"]), r["requiresAck"]): diffs.append((s["AppointmentId"], s["PaymentMethod"], s["PaymentStatus"], s["Status"]))
        check(f"decision AND version agree with the real backend code for {len(snaps)} snapshots (all payment combinations, 6-hour boundary, odd states)", len(real) == len(snaps) and not diffs, diffs[:3])
        fxp = os.path.join(a.fixtures_dir, "fixtures.json"); vp = os.path.join(a.fixtures_dir, "oracle-vectors.json")
        if os.path.exists(fxp) and os.path.exists(vp):
            fx = json.load(open(fxp)); vec = json.load(open(vp)); real_fx = run(["vectors"], json.dumps(vec["vectors"]))
            want = {x["id"]: x["expected"] for x in fx["appointments"]}; bad = [r["appointmentId"] for r in real_fx if r["version"] != want[r["appointmentId"]]["version"] or r["allowed"] != want[r["appointmentId"]]["allowed"] or r["reasonCode"] != want[r["appointmentId"]]["reasonCode"]]
            check(f"fixtures.json: decision and version of all {len(want)} seeded appointments equal the real code's", len(real_fx) == len(want) and not bad, bad)
            t = fx["targets"]["JM-05"]; r5 = next(r for r in real_fx if r["appointmentId"] == t["appointmentId"])
            check("JM-05 expectedVersion (computed offline) equals the real code's version; decision is RefundEligible, Eligible, 1500, no acknowledgement needed",
                  r5["version"] == t["expectedVersion"] and r5["reasonCode"] == "RefundEligible" and r5["refundOutcome"] == "Eligible" and float(r5["refundAmount"]) == 1500 and not r5["requiresAck"], "")
            if a.db:
                pw = os.environ.get("GCN48_DB_PASSWORD") or sys.exit("GCN48_DB_PASSWORD is not in the environment (run through gcn48-check-version.sh)")
                env = {**os.environ, "GCN48_ORACLE_CONNECTION": f"Server={HOST};Port={PORT};Database={DB};User={USER};Password={pw};"}; pat = fx["actors"]
                for jm in ("JM-01", "JM-02", "JM-05"):
                    tid = fx["targets"][jm]["appointmentId"]; got = run(["db", str(tid), pat[fx["targets"][jm]["actor"]]], env=env); exp = want[tid]
                    check(f"{jm}: the REAL service reading the seeded database row {tid} gives the stored version, decision and reason code (SELECT only)", got is not None and got["version"] == exp["version"] and got["allowed"] == exp["allowed"] and got["reasonCode"] == exp["reasonCode"], "" if got and got["version"] == exp["version"] else (got or {}).get("reasonCode"))
        else: print("  (fixtures not generated yet: the fixture comparison was skipped)")
finally: shutil.rmtree(work, ignore_errors=True)
os.makedirs(os.path.join(HERE, "evidence"), exist_ok=True)
json.dump({"passed": all(c["passed"] for c in checks), "checks": checks}, open(os.path.join(HERE, "evidence", "version-check.json"), "w"), indent=1)
print("version check: " + ("ALL CHECKS PASSED" if all(c["passed"] for c in checks) else "FAILED") + f" ({sum(c['passed'] for c in checks)}/{len(checks)})"); sys.exit(0 if all(c["passed"] for c in checks) else 1)
