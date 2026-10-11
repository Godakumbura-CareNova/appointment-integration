#!/usr/bin/env bash
# READ-ONLY evidence of what the JMeter run stored in carenova_appointment_gcn45_qa (SELECT statements only).
#   bash gcn45-db-evidence.sh <label>      e.g. after-concurrent   -> evidence/db-evidence-<label>.txt
set -u -o pipefail
. "$(dirname "$0")/gcn45-common.sh"
gcn45_assert_db_target; gcn45_load_secrets
L="${1:-manual}"; case "$L" in *[!A-Za-z0-9_-]*) gcn45_die "label may contain letters, digits, - and _ only";; esac
OUT="$GCN45_REPORT_DIR/evidence/db-evidence-$L.txt"; mkdir -p "$GCN45_REPORT_DIR/evidence"
q() { gcn45_mysql_app -t "$GCN45_DB_NAME" -e "$1"; }
{
echo "GCN-45 database evidence (read-only) $(date '+%Y-%m-%d %H:%M:%S')  database=$GCN45_DB_NAME user=$GCN45_DB_USER"
q "SELECT (SELECT COUNT(*) FROM Appointments) AS appointments, (SELECT COUNT(*) FROM AppointmentPayments) AS payments, (SELECT COUNT(*) FROM AppointmentReceipts) AS receipts, (SELECT COUNT(*) FROM AppointmentOnlinePaymentAttempts) AS attempts;"
q "SELECT Method, Status, COUNT(*) AS payments FROM AppointmentPayments GROUP BY Method, Status ORDER BY 1,2;"
q "SELECT Status, COUNT(*) AS attempts FROM AppointmentOnlinePaymentAttempts GROUP BY Status ORDER BY 1;"
echo "Duplicate checks (all must be 0):"
q "SELECT (SELECT COUNT(*) - COUNT(DISTINCT AppointmentId) FROM AppointmentPayments) AS duplicate_payments_per_appointment, (SELECT COUNT(*) - COUNT(DISTINCT GatewayReference) FROM AppointmentOnlinePaymentAttempts) AS duplicate_gateway_references, (SELECT COUNT(*) - COUNT(DISTINCT DoctorAvailabilitySlotId) FROM Appointments) AS duplicate_booked_slots, (SELECT COUNT(*) FROM AppointmentPayments p JOIN AppointmentOnlinePaymentAttempts a ON a.AppointmentPaymentId=p.Id WHERE a.Status='Succeeded' AND p.Status<>'Successful') AS succeeded_attempt_without_successful_payment;"
echo "Successful payments with more than one succeeded attempt (must be 0):"
q "SELECT COUNT(*) AS n FROM (SELECT AppointmentPaymentId FROM AppointmentOnlinePaymentAttempts WHERE Status='Succeeded' GROUP BY AppointmentPaymentId HAVING COUNT(*)>1) x;"
} 2>&1 | tee "$OUT"
