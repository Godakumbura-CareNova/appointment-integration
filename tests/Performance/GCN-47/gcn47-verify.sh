#!/usr/bin/env bash
# Runs gcn47_verify.py (pre | post | requests) with the limited user's password in the environment. READ-ONLY: SELECT statements and a log file read; NO HTTP request.
set -u -o pipefail
. "$(dirname "$0")/gcn47-common.sh"
gcn47_assert_db_target; gcn47_load_secrets
case "${1:-}" in pre|post|requests) ;; *) gcn47_die "usage: gcn47-verify.sh pre|post|requests";; esac
exec python3 "$GCN47_DIR/gcn47_verify.py" "$1"
