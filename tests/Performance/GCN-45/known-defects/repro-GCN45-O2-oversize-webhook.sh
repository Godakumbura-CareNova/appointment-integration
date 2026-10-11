#!/usr/bin/env bash
# Reproduces GCN45-O2 (expected today: FAIL = HTTP 400 instead of 413). Sends ONE oversize (70,009-byte) form body to the local TEST backend A.
# The request is rejected by the framework before the controller runs: it creates and changes nothing. No secrets, no real gateway.
BODY="$(mktemp)"; trap 'rm -f "$BODY"' EXIT
head -c 70000 /dev/zero | tr '\0' 'a' | sed 's/^/order_id=/' > "$BODY"
OUT="$(curl -s -m 10 -w '\n%{http_code}' -H 'Content-Type: application/x-www-form-urlencoded' --data-binary @"$BODY" http://localhost:5236/api/appointment-payments/payhere/notify)"
CODE="${OUT##*$'\n'}"; echo "request bytes: $(wc -c < "$BODY")   HTTP $CODE   body: $(echo "${OUT%$'\n'*}" | cut -c1-260)"
[ "$CODE" = "413" ] && echo "RESULT: PASS (413 Payload Too Large)" || { echo "RESULT: FAIL - expected 413, got $CODE (GCN45-O2 reproduced)"; exit 1; }
