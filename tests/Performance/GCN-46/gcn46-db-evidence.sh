#!/usr/bin/env bash
# READ-ONLY evidence of the isolated database (SELECT only): row counts compared with the fixtures, duplicates, and proof that the read-only run changed nothing.
#   bash gcn46-db-evidence.sh <label>      -> evidence/db-evidence-<label>.txt
set -u -o pipefail
. "$(dirname "$0")/gcn46-common.sh"
gcn46_assert_db_target; gcn46_load_secrets
L="${1:-manual}"; case "$L" in *[!A-Za-z0-9_-]*) gcn46_die "label may contain letters, digits, - and _ only";; esac
OUT="$GCN46_DIR/evidence/db-evidence-$L.txt"; mkdir -p "$GCN46_DIR/evidence"
q() { gcn46_mysql_app -t "$GCN46_DB_NAME" -e "$1"; }
EXP_A=$(python3 -c "import json;print(sum(len(p['appointments']) for p in json.load(open('$GCN46_DIR/fixtures/fixtures.json'))['patients'].values()))" 2>/dev/null || echo "?")
{
echo "GCN-46 database evidence (read-only) $(date '+%Y-%m-%d %H:%M:%S')  database=$GCN46_DB_NAME user=$GCN46_DB_USER   expected appointments from fixtures: $EXP_A"
q "SELECT (SELECT COUNT(*) FROM Appointments) AS appointments, (SELECT COUNT(*) FROM AppointmentPayments) AS payments, (SELECT COUNT(*) FROM AppointmentReceipts) AS receipts, (SELECT COUNT(*) FROM AppointmentOnlinePaymentAttempts) AS attempts;"
q "SELECT Status, COUNT(*) AS appointments FROM Appointments GROUP BY Status ORDER BY 1;"
q "SELECT COUNT(DISTINCT PatientId) AS patients_with_appointments, MIN(CreatedAtUtc) AS first_created, MAX(CreatedAtUtc) AS last_created, MAX(UpdatedAtUtc) AS last_updated FROM Appointments;"
echo "Duplicate checks (all must be 0):"
q "SELECT (SELECT COUNT(*) - COUNT(DISTINCT AppointmentReference) FROM Appointments) AS duplicate_references, (SELECT COUNT(*) - COUNT(DISTINCT DoctorAvailabilitySlotId) FROM Appointments) AS duplicate_slots, (SELECT COUNT(*) - COUNT(DISTINCT AppointmentId) FROM AppointmentPayments) AS duplicate_payments_per_appointment, (SELECT COUNT(*) FROM AppointmentPayments p JOIN Appointments a ON a.Id=p.AppointmentId WHERE a.PatientId<>p.PatientId) AS payment_owner_mismatch;"
echo "Rows touched after seeding (UpdatedAtUtc not null on appointments, must be 0 for a read-only run):"
q "SELECT COUNT(*) AS updated_appointments FROM Appointments WHERE UpdatedAtUtc IS NOT NULL;"
} 2>&1 | tee "$OUT"
