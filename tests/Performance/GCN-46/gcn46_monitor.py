#!/usr/bin/env python3
"""GCN-46 JM-07 safety monitor. Polls every few seconds while the load phase runs and asks JMeter to stop (UDP StopTestNow on the plan's own control port,
never a kill by name) when the run becomes unsafe for the machine or the data:
   1-minute load average > 9 (10-core MacBook)  |  free memory < 10 %  |  error rate over the last 10 s > 10 %  |  p95 over the last 10 s > 5000 ms  |  backend RSS > 1.5 GB
A limit must be exceeded on two consecutive polls. The reason is written to results/load/monitor-stop.txt, so the scenario is reported STOPPED, not passed.
   gcn46_monitor.py --jtl F --stop-file F --done-file F --log F --port 4546 [--backend-pid N] [--interval 5]"""
import argparse, csv, os, re, socket, subprocess, sys, time
def mem_free():
    """Free-memory percentage, or None when this OS does not report it (the check is then skipped). macOS: memory_pressure; Linux: /proc/meminfo."""
    try: return float(re.search(r"free percentage:\s*(\d+)%", subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=10).stdout).group(1))
    except Exception: pass
    try:
        m = dict(l.split(":", 1) for l in open("/proc/meminfo")); return 100.0 * int(m["MemAvailable"].split()[0]) / int(m["MemTotal"].split()[0])
    except Exception: return None
if "--probe" in sys.argv:   # used by run-gcn46-jmeter.sh before the load phase: "<1-minute load average> <free memory %, -1 if unknown>"
    f = mem_free(); print(f"{os.getloadavg()[0]:.2f} {-1 if f is None else round(f)}"); sys.exit(0)
ap = argparse.ArgumentParser()
for a in ("--jtl", "--stop-file", "--done-file", "--log"): ap.add_argument(a, required=True)
ap.add_argument("--port", type=int, default=4546); ap.add_argument("--backend-pid", type=int); ap.add_argument("--interval", type=float, default=5)
o = ap.parse_args()
LIMITS = dict(load1=float(os.environ.get("GCN46_MAX_LOAD1", "9.0")), mem_free_pct=10.0, err_pct=10.0, p95_ms=5000, rss_mb=1536)   # 9.0 = 90% of a 10-core machine; set GCN46_MAX_LOAD1 for another CPU
def load1(): return os.getloadavg()[0]
def rss_mb():
    if not o.backend_pid: return 0.0
    try: return int(subprocess.run(["ps", "-o", "rss=", "-p", str(o.backend_pid)], capture_output=True, text=True).stdout.strip() or 0) / 1024
    except Exception: return 0.0
def window():
    try:
        cut = (time.time() - 10) * 1000; rs = [r for r in csv.DictReader(open(o.jtl)) if r.get("timeStamp", "").isdigit() and int(r["timeStamp"]) >= cut]
    except Exception: return 0, 0.0, 0
    if not rs: return 0, 0.0, 0
    t = sorted(int(r["elapsed"]) for r in rs); bad = sum(r["success"] != "true" for r in rs)
    return len(rs), 100 * bad / len(rs), t[min(len(t) - 1, int(0.95 * (len(t) - 1)))]
breach = 0; log = open(o.log, "a"); log.write("time,load1,mem_free_pct,rss_mb,window_n,window_err_pct,window_p95_ms,breach\n")
while not os.path.exists(o.done_file):
    l1, mf, rs_, (n, err, p95) = load1(), mem_free(), rss_mb(), window(); why = []; mf = 100.0 if mf is None else mf
    if l1 > LIMITS["load1"]: why.append(f"load average {l1:.1f} > {LIMITS['load1']}")
    if mf < LIMITS["mem_free_pct"]: why.append(f"free memory {mf:.0f}% < {LIMITS['mem_free_pct']}%")
    if n >= 20 and err > LIMITS["err_pct"]: why.append(f"error rate {err:.1f}% > {LIMITS['err_pct']}% (last 10 s)")
    if n >= 20 and p95 > LIMITS["p95_ms"]: why.append(f"p95 {p95} ms > {LIMITS['p95_ms']} ms (last 10 s)")
    if rs_ > LIMITS["rss_mb"]: why.append(f"backend memory {rs_:.0f} MB > {LIMITS['rss_mb']} MB")
    breach = breach + 1 if why else 0
    log.write(f"{time.strftime('%H:%M:%S')},{l1:.2f},{mf:.0f},{rs_:.0f},{n},{err:.1f},{p95},{'; '.join(why)}\n"); log.flush()
    if breach >= 2:
        open(o.stop_file, "w").write("; ".join(why) + "\n")
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b"StopTestNow", ("127.0.0.1", o.port))
        log.write("STOP requested\n"); break
    time.sleep(o.interval)
