#!/usr/bin/env bash
# Generates the SQL of ALL appointment-integration migrations (empty database -> latest) into a preview file for REVIEW.
# Offline: EF's design-time factory uses a dummy connection and `migrations script` opens NO database connection.
# Release configuration only: bin/Debug of any running build is not touched. GCN-47 adds one migration (audit table), so five migrations in total.
set -u
. "$(dirname "$0")/gcn47-common.sh"
OUT="$GCN47_DIR/gcn47-migrations-preview.sql"
cd "$GCN47_REPO_ROOT" || exit 1
gcn47_check_branch
dotnet ef migrations script --configuration Release --project src/AppointmentIntegration.Api --output "$OUT" || gcn47_die "script generation failed"
echo "wrote $OUT ($(wc -l < "$OUT") lines)"
# every migration of the repository must be in the script (ids come from the Migrations folder, not from a fixed list)
MIGRATIONS="$(ls "$GCN47_REPO_API"/Migrations/*.cs 2>/dev/null | grep -vE 'Designer|Snapshot' | xargs -n1 basename | sed 's/\.cs$//')"
[ -n "$MIGRATIONS" ] || gcn47_die "no migrations found under $GCN47_REPO_API/Migrations"
for m in $MIGRATIONS; do
  grep -q "$m" "$OUT" && echo "  contains $m" || gcn47_die "migration $m is missing from the script"
done
echo "CREATE TABLE statements: $(sed 's/^\xef\xbb\xbf//' "$OUT" | grep -c '^CREATE TABLE')  (expected 6: the __EFMigrationsHistory table plus 5 data tables; the file starts with a UTF-8 byte-order mark that the mysql client ignores)"
gcn47_sql_is_safe "$OUT" || gcn47_die "the script contains a forbidden statement (listed above)"
echo "Safety scan passed (ON DELETE CASCADE in foreign keys is expected). Review the file, then: bash $GCN47_DIR/gcn47-apply-migrations.sh --yes"
