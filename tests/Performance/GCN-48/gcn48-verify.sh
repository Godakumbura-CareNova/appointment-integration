#!/usr/bin/env bash
# Runs gcn48_verify.py (pre | post | requests) with the limited user's password in the environment. READ-ONLY: SELECT statements and a log file read; NO HTTP request.
set -u -o pipefail
. "$(dirname "$0")/gcn48-common.sh"
gcn48_assert_db_target; gcn48_load_secrets
case "${1:-}" in pre|post|requests) ;; *) gcn48_die "usage: gcn48-verify.sh pre|post|requests";; esac
exec python3 "$GCN48_DIR/gcn48_verify.py" "$1"
