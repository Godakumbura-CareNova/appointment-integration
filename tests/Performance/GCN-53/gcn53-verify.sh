#!/usr/bin/env bash
# Runs gcn53_verify.py (pre | post | requests) with the limited user's password in the environment. READ-ONLY: SELECT statements and a log file read; NO HTTP request.
set -u -o pipefail
. "$(dirname "$0")/gcn53-common.sh"
gcn53_assert_db_target; gcn53_load_secrets
case "${1:-}" in pre|post|requests) ;; *) gcn53_die "usage: gcn53-verify.sh pre|post|requests";; esac
exec python3 "$GCN53_DIR/gcn53_verify.py" "$1"
