#!/usr/bin/env bash
# Creates RANDOM throw-away secrets for the GCN-45 JMeter environment:
#   JWT signing secret, PayHere TEST merchant secret (never a real PayHere credential), and the password of the limited MySQL user gcn45_qa.
# They are written ONLY to a mode-600 file in a mode-700 folder OUTSIDE every git work tree, and are never printed.
# It does not touch MySQL, services or repositories. It refuses to overwrite an existing file (the DB password would no longer match).
set -u
. "$(dirname "$0")/gcn45-common.sh"
command -v openssl >/dev/null || gcn45_die "openssl is required"
gcn45_assert_outside_git "$GCN45_SECRET_DIR"
umask 077
if [ -e "$GCN45_SECRET_FILE" ]; then echo "Secrets already exist ($GCN45_SECRET_FILE); nothing changed. Values are not shown."; exit 0; fi
mkdir -p "$GCN45_SECRET_DIR" && chmod 700 "$GCN45_SECRET_DIR"
{
  echo "# GCN-45 QA throw-away secrets. Local test use only. Never commit."
  echo "GCN45_JWT_SECRET=$(openssl rand -hex 32)"
  echo "GCN45_PAYHERE_MERCHANT_ID=TEST123"
  echo "GCN45_PAYHERE_SECRET=$(openssl rand -hex 16)"
  echo "GCN45_DB_PASSWORD=$(openssl rand -hex 20)"
} > "$GCN45_SECRET_FILE"
chmod 600 "$GCN45_SECRET_FILE"
echo "Created $GCN45_SECRET_FILE (mode 600, values not shown)."
