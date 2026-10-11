#!/usr/bin/env python3
"""GCN-45 local doctor-service STUB (QA only). Serves what appointment-integration needs from the doctor service:
   GET /api/doctors/{guid}  -> {doctorId, fullName, consultationFee, availability, upcomingSlots[...]}
It listens on 127.0.0.1 only, on 5235 by default (the GCN-49 stub on 5199 is never used or changed).
Control endpoints (used by the JMeter plan):
   GET /__mode?mode=ok|nofee|down|slow[&delay=ms][&slotBase=N][&slotCount=M]   change behaviour
   GET /__stats     {mode, requests, withBearer, withoutBearer, slotBase, slotCount}   (no token value is ever stored or logged)
   GET /__reset     zero the counters
Modes: ok (fee 2700.00), nofee (fee 0), down (HTTP 503), slow (ok after `delay` ms).
Slots: ids slotBase .. slotBase+slotCount-1, every 30 minutes starting tomorrow (UTC), so booking through the real API always has a future slot.
"""
import json, re, sys, threading, time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5235
if PORT in (3000, 5133, 5134, 5135, 5136, 5199) or PORT != 5235:
    sys.exit(f"refusing to start on port {PORT}: this stub is only for 5235")
LOCK = threading.Lock()
STATE = {"mode": "ok", "delay": 2500, "slotBase": 1, "slotCount": 300, "requests": 0, "withBearer": 0, "withoutBearer": 0}
GUID = re.compile(r"^/api/doctors/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$")


def doctor_json(doctor_id):
    start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    slots = [{"id": STATE["slotBase"] + i, "startUtc": (start + timedelta(minutes=30 * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "endUtc": (start + timedelta(minutes=30 * i + 30)).strftime("%Y-%m-%dT%H:%M:%SZ")} for i in range(STATE["slotCount"])]
    return {"doctorId": doctor_id, "fullName": "QA Dr GCN45 Stub", "consultationFee": 0 if STATE["mode"] == "nofee" else 2700.00,
            "availability": {"hasAvailableSlots": True, "availableSlotCount": len(slots), "nextAvailableSlotUtc": slots[0]["startUtc"]},
            "upcomingSlots": slots}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # never log headers or tokens
        sys.stderr.write("%s %s\n" % (self.command, urlparse(self.path).path))

    def send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path); q = parse_qs(url.query)
        if url.path == "/__mode":
            with LOCK:
                if "mode" in q:
                    if q["mode"][0] not in ("ok", "nofee", "down", "slow"): return self.send(400, {"message": "unknown mode"})
                    STATE["mode"] = q["mode"][0]
                for key in ("delay", "slotBase", "slotCount"):
                    if key in q: STATE[key] = int(q[key][0])
                return self.send(200, {k: STATE[k] for k in ("mode", "delay", "slotBase", "slotCount")})
        if url.path == "/__stats":
            with LOCK: return self.send(200, dict(STATE))
        if url.path == "/__reset":
            with LOCK: STATE.update(requests=0, withBearer=0, withoutBearer=0)
            return self.send(200, {"reset": True})
        m = GUID.match(url.path)
        if not m: return self.send(404, {"message": "not found"})
        bearer = self.headers.get("Authorization", "").startswith("Bearer ")
        with LOCK:
            STATE["requests"] += 1; STATE["withBearer" if bearer else "withoutBearer"] += 1
            mode, delay = STATE["mode"], STATE["delay"]
        if mode == "down": return self.send(503, {"message": "QA stub: doctor service is down"})
        if mode == "slow": time.sleep(delay / 1000)
        with LOCK: body = doctor_json(m.group(1))
        return self.send(200, body)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
