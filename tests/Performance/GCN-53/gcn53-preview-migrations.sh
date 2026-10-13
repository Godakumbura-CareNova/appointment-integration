#!/usr/bin/env bash
# Generates the SQL of ALL appointment-integration migrations (empty database -> latest) into a preview file for REVIEW.
# Offline: EF's design-time factory uses a dummy connection and `migrations script` opens NO database connection.
# Release configuration only: bin/Debug of any running build is not touched. GCN-53 adds one migration (AppointmentPayments.ConfirmedAtUtc column); with GCN-50 the branch has eight migrations in total.
set -u
. "$(dirname "$0")/gcn53-common.sh"
OUT="$GCN53_OUT/gcn53-migrations-preview.sql"
cd "$GCN53_REPO_ROOT" || exit 1
gcn53_check_branch
# GCN-53's Program.cs registers the DbContext even without a connection string (UseMySql("") throws when EF resolves it), so the tool gets an obviously DUMMY value for this one command:
# `migrations script` opens NO database connection and the SQL contains no database name.
ConnectionStrings__DefaultConnection="Server=127.0.0.1;Port=3306;Database=dummy_offline_script_only;User=none;Password=none;" dotnet ef migrations script --configuration Release --project src/AppointmentIntegration.Api --output "$OUT" || gcn53_die "script generation failed"
echo "wrote $OUT ($(wc -l < "$OUT") lines)"
# every migration of the repository must be in the script (ids come from the Migrations folder, not from a fixed list)
MIGRATIONS="$(ls "$GCN53_REPO_API"/Migrations/*.cs 2>/dev/null | grep -vE 'Designer|Snapshot' | xargs -n1 basename | sed 's/\.cs$//')"
[ -n "$MIGRATIONS" ] || gcn53_die "no migrations found under $GCN53_REPO_API/Migrations"
for m in $MIGRATIONS; do
  grep -q "$m" "$OUT" && echo "  contains $m" || gcn53_die "migration $m is missing from the script"
done
echo "CREATE TABLE statements: $(sed 's/^\xef\xbb\xbf//' "$OUT" | grep -c '^CREATE TABLE')  (expected 11: the __EFMigrationsHistory table plus 10 data tables; the file starts with a UTF-8 byte-order mark that the mysql client ignores)"
gcn53_sql_is_safe "$OUT" || gcn53_die "the script contains a forbidden statement (listed above)"
echo "Safety scan passed (ON DELETE CASCADE in foreign keys is expected). Review the file, then: bash $GCN53_DIR/gcn53-apply-migrations.sh --yes"
