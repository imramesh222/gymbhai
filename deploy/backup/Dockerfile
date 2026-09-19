# Nightly database backups (PLAN.md §11). pg_dump must be the server's major
# version or newer, so this starts from the same Postgres 16 image.
FROM postgres:16-alpine

RUN apk add --no-cache aws-cli tzdata

COPY backup.sh restore.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/restore.sh \
    # 02:00 in Nepal is 20:15 UTC the day before.
    && echo "15 20 * * * /usr/local/bin/backup.sh >> /proc/1/fd/1 2>&1" > /etc/crontabs/root

CMD ["crond", "-f", "-l", "8"]
