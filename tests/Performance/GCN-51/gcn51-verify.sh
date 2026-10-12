#!/usr/bin/env bash
# Runs gcn51_verify.py (pre | post | requests) with the limited user's password in the environment. READ-ONLY: SELECT statements and a log file read; NO HTTP request.
set -u -o pipefail
. "$(dirname "$0")/gcn51-common.sh"
gcn51_assert_db_target; gcn51_load_secrets
case "${1:-}" in pre|post|requests) ;; *) gcn51_die "usage: gcn51-verify.sh pre|post|requests";; esac
exec python3 "$GCN51_DIR/gcn51_verify.py" "$1"
