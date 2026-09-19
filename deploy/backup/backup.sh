#!/bin/sh
# Dump the database, upload it to BACKUP_BUCKET, delete dumps older than
# BACKUP_KEEP_DAYS. Run by cron at 02:00 Nepal time; safe to run by hand:
#   docker compose -f docker-compose.prod.yml exec backup backup.sh
set -eu

: "${BACKUP_BUCKET:?BACKUP_BUCKET is not set}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
STAMP="$(date -u +%Y-%m-%dT%H%M%SZ)"
FILE="/tmp/gymbhai-${STAMP}.dump"
S3="aws s3 --endpoint-url ${S3_ENDPOINT_URL}"

export AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${S3_SECRET_ACCESS_KEY}"
export AWS_DEFAULT_REGION="${S3_REGION:-auto}"
export PGPASSWORD="${POSTGRES_PASSWORD}"

echo "backup: dumping ${POSTGRES_DB}"
# Custom format: compressed, and pg_restore can restore it table by table.
pg_dump --format=custom --no-owner -h db -U "${POSTGRES_USER}" "${POSTGRES_DB}" > "${FILE}"
$S3 cp "${FILE}" "s3://${BACKUP_BUCKET}/db/gymbhai-${STAMP}.dump"
rm -f "${FILE}"
echo "backup: uploaded gymbhai-${STAMP}.dump"

CUTOFF="$(date -u -d "@$(( $(date +%s) - KEEP_DAYS * 86400 ))" +%Y-%m-%dT%H%M%SZ)"
$S3 ls "s3://${BACKUP_BUCKET}/db/" | awk '{print $4}' | while read -r name; do
  stamp="${name#gymbhai-}"
  stamp="${stamp%.dump}"
  if [ -n "${stamp}" ] && [ "${stamp}" \< "${CUTOFF}" ]; then
    $S3 rm "s3://${BACKUP_BUCKET}/db/${name}"
    echo "backup: removed ${name}"
  fi
done
