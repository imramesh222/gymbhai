#!/bin/sh
# Restore a backup into a database. Test this once before the first real gym
# goes live (PLAN.md §11), into a scratch database:
#   docker compose -f docker-compose.prod.yml exec backup \
#       restore.sh gymbhai-2026-10-01T201500Z.dump gymbhai_restore_test
# Restoring over the live database means stopping api and worker first and
# giving its name as the second argument. Nothing here does that for you.
set -eu

NAME="${1:?Give the dump file name (see: aws s3 ls s3://BUCKET/db/)}"
TARGET="${2:?Give the database to restore into}"
S3="aws s3 --endpoint-url ${S3_ENDPOINT_URL}"

export AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${S3_SECRET_ACCESS_KEY}"
export AWS_DEFAULT_REGION="${S3_REGION:-auto}"
export PGPASSWORD="${POSTGRES_PASSWORD}"

$S3 cp "s3://${BACKUP_BUCKET}/db/${NAME}" "/tmp/${NAME}"
createdb -h db -U "${POSTGRES_USER}" "${TARGET}" 2>/dev/null || true
pg_restore --clean --if-exists --no-owner -h db -U "${POSTGRES_USER}" -d "${TARGET}" "/tmp/${NAME}"
rm -f "/tmp/${NAME}"
echo "restored ${NAME} into ${TARGET}"
psql -h db -U "${POSTGRES_USER}" -d "${TARGET}" -tAc \
  "select 'gyms: ' || count(*) from gyms union all select 'members: ' || count(*) from members"
