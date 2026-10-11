#!/usr/bin/env bash
# Creates RANDOM throw-away secrets for the GCN-47 JMeter environment: a JWT signing secret and the password of the limited MySQL user gcn47_qa.
# Written ONLY to a mode-600 file in a mode-700 folder OUTSIDE every git work tree; never printed. It does not touch MySQL, services or repositories.
# It refuses to overwrite an existing file (the database password would no longer match). It never reads or reuses GCN-45 secrets.
set -u
. "$(dirname "$0")/gcn47-common.sh"
command -v openssl >/dev/null || gcn47_die "openssl is required"
gcn47_assert_outside_git "$GCN47_SECRET_DIR"
umask 077
if [ -e "$GCN47_SECRET_FILE" ]; then echo "Secrets already exist ($GCN47_SECRET_FILE); nothing changed. Values are not shown."; exit 0; fi
mkdir -p "$GCN47_SECRET_DIR" && chmod 700 "$GCN47_SECRET_DIR"
{
  echo "# GCN-47 QA throw-away secrets. Local test use only. Never commit."
  echo "GCN47_JWT_SECRET=$(openssl rand -hex 32)"
  echo "GCN47_DB_PASSWORD=$(openssl rand -hex 20)"
} > "$GCN47_SECRET_FILE"
chmod 600 "$GCN47_SECRET_FILE"
echo "Created $GCN47_SECRET_FILE (mode 600, values not shown)."
