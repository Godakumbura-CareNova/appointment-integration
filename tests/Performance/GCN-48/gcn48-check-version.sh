#!/usr/bin/env bash
# Offline check of the confirmation versions against the REAL backend code (published build). No HTTP request; no database write.
#   bash gcn48-check-version.sh [API_DIR]          API_DIR defaults to the published build of the run folder (created by start-gcn48-env.sh)
#   bash gcn48-check-version.sh [API_DIR] --db     after seeding: the real service also reads the seeded rows (SELECT only) and its versions must equal fixtures.json
set -u -o pipefail
. "$(dirname "$0")/gcn48-common.sh"
API="${1:-$GCN48_RUN_DIR/app}"; [ "${1:-}" = "--db" ] && API="$GCN48_RUN_DIR/app"
EXTRA=""; for x in "$@"; do [ "$x" = "--db" ] && EXTRA="--db"; done
if [ -n "$EXTRA" ]; then gcn48_assert_db_target; gcn48_load_secrets; fi
exec python3 "$GCN48_DIR/gcn48_check_version.py" --api-dir "$API" $EXTRA
