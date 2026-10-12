#!/usr/bin/env bash
# Creates RANDOM throw-away secrets for the GCN-48 JMeter environment: a JWT signing secret and the password of the limited MySQL user gcn48_qa.
# Written ONLY to a mode-600 file in a mode-700 folder OUTSIDE every git work tree; never printed. It does not touch MySQL, services or repositories.
# It refuses to overwrite an existing file (the database password would no longer match). It never reads or reuses GCN-45 secrets.
set -u
. "$(dirname "$0")/gcn48-common.sh"
command -v openssl >/dev/null || gcn48_die "openssl is required"
gcn48_assert_outside_git "$GCN48_SECRET_DIR"
umask 077
if [ -e "$GCN48_SECRET_FILE" ]; then echo "Secrets already exist ($GCN48_SECRET_FILE); nothing changed. Values are not shown."; exit 0; fi
mkdir -p "$GCN48_SECRET_DIR" && chmod 700 "$GCN48_SECRET_DIR"
{
  echo "# GCN-48 QA throw-away secrets. Local test use only. Never commit."
  echo "GCN48_JWT_SECRET=$(openssl rand -hex 32)"
  echo "GCN48_DB_PASSWORD=$(openssl rand -hex 20)"
} > "$GCN48_SECRET_FILE"
chmod 600 "$GCN48_SECRET_FILE"
echo "Created $GCN48_SECRET_FILE (mode 600, values not shown)."
