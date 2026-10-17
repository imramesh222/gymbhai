#!/bin/sh
# A base backup for point-in-time restores (PLAN.md §11): full on Saturday,
# the gym's quiet day, differential the rest of the week. Run by cron at
# 02:30 Nepal time; safe to run by hand, choosing the kind if you like:
#   docker compose -f docker-compose.prod.yml exec backup base-backup.sh [full|diff]
set -eu
. /usr/local/bin/pgbackrest-env.sh

case "${1:-}" in
  full | diff) TYPE="$1" ;;
  "") if [ "$(TZ=Asia/Kathmandu date +%u)" = "6" ]; then TYPE="full"; else TYPE="diff"; fi ;;
  *) echo "base-backup: full or diff, not '$1'" >&2; exit 2 ;;
esac
echo "base-backup: ${TYPE}"
su-exec postgres pgbackrest --type="${TYPE}" backup
su-exec postgres pgbackrest info
