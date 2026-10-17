# pgBackRest settings, from the S3 values the rest of the stack already uses
# (.env.prod). Sourced by every script here and by the database's
# archive_command, so all of them agree on where the archive lives.
#
# The archive is in BACKUP_BUCKET under /pgbackrest, next to the nightly
# pg_dump files under /db.

# "https://<account>.r2.cloudflarestorage.com" -> host (and port, if any).
_s3_host="${S3_ENDPOINT_URL#*://}"
_s3_host="${_s3_host%%/*}"
case "${_s3_host}" in
  *:*)
    export PGBACKREST_REPO1_STORAGE_PORT="${_s3_host##*:}"
    _s3_host="${_s3_host%:*}"
    ;;
esac

export PGBACKREST_STANZA=gymbhai
export PGBACKREST_REPO1_TYPE=s3
export PGBACKREST_REPO1_PATH=/pgbackrest
export PGBACKREST_REPO1_S3_BUCKET="${BACKUP_BUCKET}"
export PGBACKREST_REPO1_S3_ENDPOINT="${_s3_host}"
export PGBACKREST_REPO1_S3_REGION="${S3_REGION:-auto}"
export PGBACKREST_REPO1_S3_KEY="${S3_ACCESS_KEY_ID}"
export PGBACKREST_REPO1_S3_KEY_SECRET="${S3_SECRET_ACCESS_KEY}"
export PGBACKREST_REPO1_S3_URI_STYLE=path
# A full backup every week (base-backup.sh): two of them, with everything in
# between, means any moment of the last 7 to 14 days can be restored.
export PGBACKREST_REPO1_RETENTION_FULL=2
export PGBACKREST_PG1_PATH=/var/lib/postgresql/data
export PGBACKREST_PG1_USER="${POSTGRES_USER}"
export PGBACKREST_PG1_DATABASE="${POSTGRES_DB}"
export PGBACKREST_COMPRESS_TYPE=zst
export PGBACKREST_START_FAST=y
export PGBACKREST_LOG_LEVEL_FILE=off
# A restored database fetches WAL through this wrapper, which brings these
# settings with it: the server's own environment doesn't have them.
export PGBACKREST_RECOVERY_OPTION='restore_command=/usr/local/bin/pgbackrest-archive-get.sh %f "%p"'
export PGBACKREST_LOG_LEVEL_CONSOLE="${PGBACKREST_LOG_LEVEL_CONSOLE:-info}"
unset _s3_host
