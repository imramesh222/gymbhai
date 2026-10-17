#!/bin/sh
# The restore_command of every restored database (pgbackrest-env.sh): WAL
# comes back from the archive with the same settings it went in with.
. /usr/local/bin/pgbackrest-env.sh
# Postgres runs this from the data directory, which for a scratch restore
# (restore-to-time.sh) isn't the live one.
exec pgbackrest --pg1-path="$(pwd)" archive-get "$1" "$2"
