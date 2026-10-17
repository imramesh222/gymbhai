#!/bin/sh
# See the database as it was at a moment in the last 7 days (PLAN.md §11).
#
#   docker compose -f docker-compose.prod.yml exec backup \
#       restore-to-time.sh "2026-10-17 14:05:00+05:45"
#
# Restores into a scratch directory, starts a throwaway Postgres on it, prints
# a few counts and keeps it running on port 5499 inside this container so you
# can look around (psql -h /tmp -p 5499). Stop it with:
#   su-exec postgres pg_ctl -D /tmp/pitr stop
# It never touches the live database. Putting a restore live is a separate,
# deliberate step: docs/DEPLOY.md §7.
set -eu
. /usr/local/bin/pgbackrest-env.sh

TIME="${1:?Give the moment, e.g. \"2026-10-17 14:05:00+05:45\"}"
TARGET=/tmp/pitr

if [ -f "${TARGET}/postmaster.pid" ]; then
  su-exec postgres pg_ctl -D "${TARGET}" -m fast stop || true
fi
rm -rf "${TARGET}"
mkdir -p "${TARGET}"
chown postgres:postgres "${TARGET}"
chmod 700 "${TARGET}"

su-exec postgres pgbackrest --pg1-path="${TARGET}" \
  --type=time --target="${TIME}" --target-action=promote restore
# Archiving stays off (it is only switched on for the live server, on its
# command line), so this copy can never write into the archive.
su-exec postgres pg_ctl -D "${TARGET}" -w -t 600 \
  -o "-p 5499 -k /tmp -c listen_addresses=''" start

su-exec postgres psql -h /tmp -p 5499 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc \
  "select 'restored to: ' || coalesce(pg_last_xact_replay_timestamp()::text, 'the backup itself')"
echo "restored ${POSTGRES_DB} as of ${TIME}: psql -h /tmp -p 5499 -U ${POSTGRES_USER} ${POSTGRES_DB}"
