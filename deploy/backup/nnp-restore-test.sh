#!/usr/bin/env bash
# Restore the latest backup to a scratch dir and verify it: the SQLite snapshot
# must open, pass PRAGMA integrity_check, and have rows. An untested backup is
# not a backup. Run this on the server after the first successful backup, and
# occasionally thereafter.
#
# Needs the same environment as nnp-backup.sh. For a manual run:
#   set -a; . /etc/nnp-backup.env; set +a; ./nnp-restore-test.sh
set -euo pipefail

: "${RESTIC_REPOSITORY:?set RESTIC_REPOSITORY}"

target="$(mktemp -d)"
trap 'rm -rf "$target"' EXIT

restic restore latest --target "$target"

db="$(find "$target" -name app.db | head -n1)"
[ -n "$db" ] || { echo "no app.db found in the restored snapshot" >&2; exit 1; }

integ="$(sqlite3 "$db" 'PRAGMA integrity_check;')"
[ "$integ" = "ok" ] || { echo "restored db failed integrity_check: $integ" >&2; exit 1; }

entries="$(sqlite3 "$db" 'SELECT count(*) FROM entries;')"
echo "restore OK: integrity ok, $entries entries in the restored database"
