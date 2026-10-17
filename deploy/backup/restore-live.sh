#!/bin/sh
# Put the LIVE database back as it was at a moment (docs/DEPLOY.md §8). Only
# for a disaster: everything written after that moment is gone. Run in the
# stopped database's place:
#   $C stop api worker web backup db
#   $C run --rm --no-deps --entrypoint restore-live.sh db "2026-10-17 14:05:00+05:45"
#   $C up -d
#   $C exec backup base-backup.sh full
# "latest" instead of a moment restores everything the archive has: a new
# server after the old one is lost, before its first start.
# Look first with restore-to-time.sh, which never touches the live database.
set -eu
. /usr/local/bin/pgbackrest-env.sh

TIME="${1:?Give the moment, e.g. \"2026-10-17 14:05:00+05:45\", or latest}"
if [ -f "${PGBACKREST_PG1_PATH}/postmaster.pid" ]; then
  echo "restore-live: the database is still running. Stop it first." >&2
  exit 1
fi
mkdir -p "${PGBACKREST_PG1_PATH}"
chown postgres:postgres "${PGBACKREST_PG1_PATH}"
chmod 700 "${PGBACKREST_PG1_PATH}"
# --delta rewrites only the files that differ from the backup (all of them
# into an empty directory).
if [ "${TIME}" = "latest" ]; then
  su-exec postgres pgbackrest --delta restore
else
  su-exec postgres pgbackrest --delta \
    --type=time --target="${TIME}" --target-action=promote restore
fi
echo "restore-live: done. Start everything, then take a full backup."
