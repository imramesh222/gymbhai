#!/bin/sh
# The database's archive_command (docker-compose.prod.yml): each finished WAL
# segment goes to the archive. A failure leaves the segment in pg_wal and
# Postgres tries again, so nothing is lost while R2 is unreachable.
. /usr/local/bin/pgbackrest-env.sh
exec pgbackrest archive-push "$1"
