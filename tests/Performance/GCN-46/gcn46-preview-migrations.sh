#!/usr/bin/env bash
# Generates the SQL of ALL appointment-integration migrations (empty database -> latest) into a preview file for REVIEW.
# Offline: EF's design-time factory uses a dummy connection and `migrations script` opens NO database connection.
# Release configuration only: bin/Debug of any running build is not touched. GCN-46 adds no migration, so the four existing ones are expected.
set -u
. "$(dirname "$0")/gcn46-common.sh"
OUT="$GCN46_DIR/gcn46-migrations-preview.sql"
cd "$GCN46_REPO_ROOT" || exit 1
gcn46_check_branch
dotnet ef migrations script --configuration Release --project src/AppointmentIntegration.Api --output "$OUT" || gcn46_die "script generation failed"
echo "wrote $OUT ($(wc -l < "$OUT") lines)"
# every migration of the repository must be in the script (ids come from the Migrations folder, not from a fixed list)
MIGRATIONS="$(ls "$GCN46_REPO_API"/Migrations/*.cs 2>/dev/null | grep -vE 'Designer|Snapshot' | xargs -n1 basename | sed 's/\.cs$//')"
[ -n "$MIGRATIONS" ] || gcn46_die "no migrations found under $GCN46_REPO_API/Migrations"
for m in $MIGRATIONS; do
  grep -q "$m" "$OUT" && echo "  contains $m" || gcn46_die "migration $m is missing from the script"
done
echo "CREATE TABLE statements: $(sed 's/^\xef\xbb\xbf//' "$OUT" | grep -c '^CREATE TABLE')  (expected 5 with the history table; the file starts with a UTF-8 byte-order mark that the mysql client ignores)"
gcn46_sql_is_safe "$OUT" || gcn46_die "the script contains a forbidden statement (listed above)"
echo "Safety scan passed (ON DELETE CASCADE in foreign keys is expected). Review the file, then: bash $GCN46_DIR/gcn46-apply-migrations.sh --yes"
