#!/bin/sh
# The backup container: make sure the archive exists, then run cron.
set -eu
. /usr/local/bin/pgbackrest-env.sh

# Once per new archive; harmless afterwards. Until it has run, the database's
# WAL waits in pg_wal (archive_command fails and is retried).
until su-exec postgres pgbackrest stanza-create; do
  echo "start: waiting for the database and the archive"
  sleep 10
done
su-exec postgres pgbackrest check
exec crond -f -l 8
