#!/usr/bin/env bash
# Generates the SQL of ALL appointment-integration migrations (empty database -> latest) into a preview file for REVIEW.
# Offline: EF's design-time factory uses a dummy connection and `migrations script` opens NO database connection.
# It builds in the Release configuration only, so bin/Debug of the running GCN-49 backend (:5136) is not touched.
# Output: gcn45-migrations-preview.sql (no password, no secret). Then it scans the file and lists the four expected migrations.
set -u
. "$(dirname "$0")/gcn45-common.sh"
OUT="$GCN45_REPORT_DIR/gcn45-migrations-preview.sql"
cd "$GCN45_REPO_ROOT" || exit 1
git rev-parse --abbrev-ref HEAD | grep -qx "feature/GCN-45-appointment-payment" || gcn45_die "the repository is not on feature/GCN-45-appointment-payment"
dotnet ef migrations script --configuration Release --project src/AppointmentIntegration.Api --output "$OUT" || gcn45_die "script generation failed"
echo "wrote $OUT ($(wc -l < "$OUT") lines)"
for m in 20261006174540_InitialAppointmentBooking 20261007031240_GCN45AppointmentPayments 20261007041047_GCN45AppointmentReceipts 20261007054830_GCN45OnlinePaymentAttempts; do
  grep -q "$m" "$OUT" && echo "  contains $m" || gcn45_die "migration $m is missing from the script"
done
echo "CREATE TABLE statements: $(grep -c '^CREATE TABLE' "$OUT")  (expected 5 with the history table)"
gcn45_sql_is_safe "$OUT" || gcn45_die "the script contains a forbidden statement (listed above)"
echo "Safety scan: no DROP/DELETE/TRUNCATE/UPDATE/GRANT/RENAME/CREATE DATABASE/USER/USE found (ON DELETE CASCADE in foreign keys is expected). Review the file, then: bash $GCN45_REPORT_DIR/gcn45-apply-migrations.sh --yes"
