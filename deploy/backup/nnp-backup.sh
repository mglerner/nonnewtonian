#!/usr/bin/env bash
# Nightly encrypted off-site backup for NonNewtonian Physicists: a CONSISTENT
# SQLite snapshot + the photos dir, pushed to a restic repo (Backblaze B2 by
# default). Run by nnp-backup.timer; all config comes from the systemd
# EnvironmentFile (see nnp-backup.env.example).
#
# This script is meant to run ON THE SERVER, by you. It is committed here as
# deploy tooling; nothing in this repo connects to your server for you.
set -euo pipefail

: "${NNP_DB:?set NNP_DB to the sqlite database path}"
: "${NNP_PHOTOS:?set NNP_PHOTOS to the photos directory}"
: "${RESTIC_REPOSITORY:?set RESTIC_REPOSITORY (e.g. b2:bucket:nnp)}"
# restic reads RESTIC_PASSWORD / RESTIC_PASSWORD_FILE and the B2_* creds from
# the environment; systemd's EnvironmentFile supplies them.

staging="${NNP_BACKUP_STAGING:-/var/lib/nnp/backup-staging}"
mkdir -p "$staging"
snap="$staging/app.db"
# A STABLE staging path (not mktemp) so the backed-up path is predictable for
# restore. The plaintext copy is removed on exit.
trap 'rm -f "$snap"' EXIT

# Consistent snapshot: sqlite's online-backup API copies a coherent image even
# while the app is mid-write in WAL mode. NEVER back up the live app.db by file
# copy -- you can capture a torn, half-written page and not know until restore.
sqlite3 "$NNP_DB" ".backup '$snap'"

# Fail loudly if the snapshot itself is already corrupt -- don't ship a bad backup.
integ="$(sqlite3 "$snap" 'PRAGMA integrity_check;')"
[ "$integ" = "ok" ] || { echo "snapshot integrity_check failed: $integ" >&2; exit 1; }

restic backup --tag nnp "$snap" "$NNP_PHOTOS"

restic forget --tag nnp \
  --keep-daily "${KEEP_DAILY:-7}" \
  --keep-weekly "${KEEP_WEEKLY:-4}" \
  --keep-monthly "${KEEP_MONTHLY:-6}" \
  --prune

echo "nnp backup complete: $(date -u +%FT%TZ)"
