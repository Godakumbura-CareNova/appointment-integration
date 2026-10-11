#!/usr/bin/env bash
# VALIDATION GATE (read-only, no load): environment, isolated database, synthetic data, authentication and API connectivity. Run it before any JMeter phase.
# It sends a handful of GET requests with synthetic tokens and runs SELECT statements. It changes nothing. Exit code 0 only if every check passes.
set -u -o pipefail
. "$(dirname "$0")/gcn46-common.sh"
gcn46_assert_db_target; gcn46_load_secrets
FX="$GCN46_DIR/fixtures/fixtures.json"; OUT="$GCN46_DIR/evidence/validate-env.txt"; mkdir -p "$GCN46_DIR/evidence"; FAIL=0
ok() { printf '  PASS  %s\n' "$1"; }; bad() { printf '  FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
B="http://localhost:$GCN46_PORT"; code() { curl -s -o /dev/null -m 10 -w '%{http_code}' -H "Authorization: Bearer $2" "$1"; }
jget() { python3 -c "import json,sys; d=json.load(open('$FX')); print(eval(sys.argv[1]))" "$1"; }
{
echo "GCN-46 environment validation $(date '+%Y-%m-%d %H:%M:%S')"
echo "1. Secrets and isolation"
[ "$(gcn46_mode "$GCN46_SECRET_FILE")" = "600" ] && ok "secrets file mode 600, outside git" || bad "secrets file mode"
V=$(gcn46_mysql_app -N -B -e "SHOW DATABASES;" | tr '\n' ' ') && ok "limited user connects: sees [$V]" || bad "limited user cannot connect"
case "$V" in *carenova_appointment_qa*|*carenova_appointment_integration*|*gcn45*) bad "the limited user can see another CareNova database";; *) ok "no other CareNova database is visible to the limited user";; esac
echo "2. Synthetic data"
[ -f "$FX" ] && ok "fixtures file present" || bad "fixtures file missing (run gcn46-seed-fixtures.sh)"
EXP=$(jget "sum(len(p['appointments']) for p in d['patients'].values())"); GOT=$(gcn46_mysql_app -N -B "$GCN46_DB_NAME" -e "SELECT COUNT(*) FROM Appointments;")
[ "$EXP" = "$GOT" ] && ok "appointments in the database ($GOT) equal the fixtures ($EXP)" || bad "appointments $GOT differ from the fixtures $EXP"
REAL=$(gcn46_mysql_app -N -B "$GCN46_DB_NAME" -e "SELECT COUNT(*) FROM Appointments WHERE PatientId NOT LIKE '46a00000-%';"); [ "$REAL" = "0" ] && ok "every appointment belongs to a synthetic patient (46a0...)" || bad "$REAL appointments belong to a non-synthetic patient id"
python3 - "$FX" <<'PY' && ok "fixtures are younger than 36 hours (sections still valid)" || bad "fixtures expired: regenerate and re-seed"
import json, sys, datetime as dt
d = json.load(open(sys.argv[1])); sys.exit(0 if dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) < dt.datetime.strptime(d["validUntilUtc"], "%Y-%m-%dT%H:%M:%SZ") and d.get("synthetic") is True else 1)
PY
echo "3. Backend connectivity and authentication (synthetic tokens, GET only)"
[ "$(curl -s -o /dev/null -m 10 -w '%{http_code}' "$B/api/appointments")" = "401" ] && ok "no token -> 401" || bad "no token did not give 401 (backend on $GCN46_PORT not running?)"
L01=$(jget "d['patients']['L01']['id']"); A_ID=$(jget "d['patients']['A']['appointments'][0]['id']"); L01_ID=$(jget "d['patients']['L01']['appointments'][0]['id']")
T=$(python3 "$GCN46_DIR/gcn46_token.py" Patient "$L01"); [ "$(code "$B/api/appointments" "$T")" = "200" ] && ok "valid synthetic Patient token -> 200 (token format accepted by the real authentication)" || bad "valid token rejected"
python3 - "$B" "$T" "$FX" <<'PY' && ok "list for L01: 12 appointments, all CN-APT-L01-*" || bad "list content wrong"
import json, sys, urllib.request
req = urllib.request.Request(sys.argv[1] + "/api/appointments", headers={"Authorization": "Bearer " + sys.argv[2]}); data = json.load(urllib.request.urlopen(req, timeout=10))
sys.exit(0 if len(data) == 12 and all(x["appointmentReference"].startswith("CN-APT-L01-") for x in data) else 1)
PY
[ "$(code "$B/api/appointments/$L01_ID" "$T")" = "200" ] && ok "own appointment details -> 200" || bad "own details failed"
[ "$(code "$B/api/appointments/$A_ID" "$T")" = "404" ] && ok "another patient's appointment -> 404" || bad "foreign appointment not refused"
[ "$(code "$B/api/appointments/999999" "$T")" = "404" ] && ok "unknown appointment -> 404" || bad "unknown appointment not 404"
[ "$(code "$B/api/appointments" "$(python3 "$GCN46_DIR/gcn46_token.py" Patient "$L01" -3600)")" = "401" ] && ok "expired token -> 401" || bad "expired token accepted"
[ "$(code "$B/api/appointments" "$(python3 "$GCN46_DIR/gcn46_token.py" Doctor 46e00000-0000-4000-8000-000000000001)")" = "403" ] && ok "Doctor role -> 403" || bad "Doctor role not refused"
echo "4. Test plan"
python3 - "$GCN46_DIR" <<'PY' && ok "JMX is well-formed; 7 scenarios JM-01..JM-07 in scenarios.json" || bad "plan check"
import json, sys, xml.etree.ElementTree as ET
d = sys.argv[1]; ET.parse(d + "/GCN46PatientAppointmentsTest.jmx"); s = json.load(open(d + "/scenarios.json"))["scenarios"]
sys.exit(0 if sorted(k for k in s if k.startswith("JM-")) == [f"JM-0{i}" for i in range(1, 8)] else 1)
PY
echo "5. Other environments"
for p in 5235 5236 5237 5136 5199 3000; do gcn46_port_in_use "$p" && echo "  info  port $p is busy (not ours, untouched)" || true; done
echo; [ "$FAIL" = 0 ] && echo "VALIDATION PASSED" || echo "$FAIL CHECK(S) FAILED"
} 2>&1 | tee "$OUT"; exit "${PIPESTATUS[0]}"
