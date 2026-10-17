# The database and its backups (PLAN.md §11). One image for both services in
# docker-compose.prod.yml: `db` runs Postgres with WAL archiving to R2
# (pgbackrest-archive-push.sh); `backup` runs cron for base backups and the nightly pg_dump.
# pg_dump must be the server's major version or newer, so this starts from
# the same Postgres 16 image.
FROM postgres:16-alpine

RUN apk add --no-cache aws-cli pgbackrest tzdata

COPY pgbackrest-env.sh pgbackrest-archive-push.sh pgbackrest-archive-get.sh \
     base-backup.sh backup.sh restore.sh restore-to-time.sh restore-live.sh \
     start.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/*.sh \
    # 02:00 and 02:30 in Nepal are 20:15 and 20:45 UTC the day before.
    && printf '%s\n' \
       "15 20 * * * /usr/local/bin/backup.sh >> /proc/1/fd/1 2>&1" \
       "45 20 * * * /usr/local/bin/base-backup.sh >> /proc/1/fd/1 2>&1" \
       > /etc/crontabs/root

CMD ["start.sh"]
