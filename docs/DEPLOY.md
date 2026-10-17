# Deploying GymBhai

How to put GymBhai on a server for the pilot (PLAN.md §12 M5, §13), and keep it
running. One VPS runs everything with Docker Compose; Caddy in front handles
HTTPS. Postgres runs on the same machine, backed up every night to a bucket
elsewhere.

What you need first — none of this can be done from the code:

| | What | Notes |
|---|---|---|
| 1 | A VPS | 2 vCPU, 4 GB RAM, 40 GB disk is plenty for the pilot. Ubuntu 24.04. |
| 2 | The domain | `gymbhai.com`, with DNS you control. |
| 3 | An S3-compatible bucket account | Cloudflare R2: two buckets, `gymbhai-files` and `gymbhai-backups`, and an API token for both. |
| 4 | An SMS gateway account | Sparrow or Aakash, with credit. Apply for sender IDs early: approval takes time (PLAN.md §10). |
| 5 | An email account for sending | Any SMTP provider. Member sign-in codes by email are free for gyms. |
| 6 | Optional: Sentry | A free project for error alerts. |
| 7 | An uptime check | Any service that fetches `https://app.gymbhai.com/health/ready` every few minutes. |

## 1. The server

```sh
# As root on a fresh Ubuntu server
apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh
adduser --disabled-password gymbhai && usermod -aG docker gymbhai
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
```

Point DNS at the server: an `A` record for `app.gymbhai.com` and for
`gymbhai.com`. Caddy fetches the certificates itself once DNS resolves.

## 2. The code and settings

```sh
su - gymbhai
git clone <your repository> gymbhai && cd gymbhai
cp .env.prod.example .env.prod
chmod 600 .env.prod
```

Fill in `.env.prod`. Every setting is explained in the file. The ones that
must not stay empty: `POSTGRES_PASSWORD`, `SECRET_KEY` (the app refuses to
start with the development one), `TOTP_KEY` (a second random value, never
changed afterwards: it would break everyone's authenticator app), the S3 keys
and buckets, and the domains.

Keep `SMS_PROVIDER=console` until you have tested the gateway (step 5).

## 3. Start it

```sh
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.prod ps
curl https://app.gymbhai.com/health/ready     # {"status":"ok","database":"ok"}
```

The API applies database migrations every time it starts.

Create the platform admin account (you), then sign in at
`https://app.gymbhai.com/staff/login` — it opens `/admin`:

```sh
docker compose -f docker-compose.prod.yml --env-file .env.prod exec api \
  python -m scripts.create_platform_admin --name "Ramesh" --email you@example.com
```

In `/admin → Our plans and prices`, add your plans. Prices live only there
(PLAN.md §15). New gyms get a 14-day trial whether or not a price is set.

## 4. Backups — test both restores before the first real gym

Two kinds, both in `BACKUP_BUCKET` (PLAN.md §11):

- **Continuous:** the database sends every WAL segment to R2 as it is
  written, at least once a minute, and the `backup` container takes a base
  backup at 02:30 Nepal time (full on Saturday, differential otherwise). Any
  moment of the last 7–14 days can be restored. Under `/pgbackrest`.
- **Nightly `pg_dump`** at 02:00, kept `BACKUP_KEEP_DAYS`: a plain file you
  can take anywhere. Under `/db`.

The `backup` container creates the archive when it first starts
(`$C logs backup` should end with `check command end: completed
successfully`). Take the first full backup now, then prove both restores:

```sh
C="docker compose -f docker-compose.prod.yml --env-file .env.prod"
$C exec backup base-backup.sh full

# Point in time: a few minutes from now, after making a change you'll look for.
$C exec backup restore-to-time.sh "2026-10-17 14:05:00+05:45"
$C exec backup sh -c 'su-exec postgres psql -h /tmp -p 5499 -U "$POSTGRES_USER" "$POSTGRES_DB"'
$C exec backup su-exec postgres pg_ctl -D /tmp/pitr stop

# The nightly dump.
$C exec backup backup.sh
$C exec backup sh -c 'aws s3 --endpoint-url "$S3_ENDPOINT_URL" ls "s3://$BACKUP_BUCKET/db/"'
$C exec backup restore.sh gymbhai-<stamp>.dump gymbhai_restore_test
$C exec db sh -c 'dropdb -U "$POSTGRES_USER" gymbhai_restore_test'
```

`restore-to-time.sh` restores into a scratch directory inside the `backup`
container and starts a throwaway Postgres there; it never touches the live
database. `restore.sh` prints the number of gyms and members it found.

## 5. SMS and email, live

The Sparrow and Aakash adapters follow those gateways' published APIs but
have not been run against a live account. Before switching:

1. Give the gateway this server's IP address: Sparrow answers only calls from
   addresses whitelisted on the account (error 1001 otherwise).
2. Set `SMS_PROVIDER=sparrow` (or `aakash`) and its token in `.env.prod`,
   and remove `MASTER_OTP`: it is only for while there is no gateway, and the
   app refuses to start with both.
   `SPARROW_SENDER` is the identity Sparrow gives the account, not a name you
   choose: their shared sender until your own sender ID is approved.
3. Restart: `$C up -d api worker`.
4. Check the account before spending anything:
   `$C exec api python -m scripts.sms_check` — it reads the credit balance,
   which proves the token, the sender and the whitelisting. Add
   `--to 98XXXXXXXX` to send one real message (costs a credit).
5. Sign up a test gym with your own phone, add yourself as a member, and
   check the welcome SMS arrives. Then sign in to the member app with the code.
6. Check the SMS log in the staff dashboard shows it as **Sent**.

Do the same for email with `EMAIL_PROVIDER=smtp`, using a member with an email.

**Help button:** set `SUPPORT_WHATSAPP` in `.env.prod` to our WhatsApp/Viber number, digits with the country code (`9779800000000`). Without it, Help shows only the guides.

**Notifications on members' phones** (free, instead of SMS) need a key, made
once and kept: `make vapid` on your machine, then `VAPID_PRIVATE_KEY=…` and
`PUSH_PROVIDER=webpush` in `.env.prod`. A new key later means every member has
to turn reminders on again. Check it: open the member app on an Android phone
in Chrome, tap **Turn on**, then publish a notice with *Also send to their
phones* — it should arrive as a notification, and the notice should say
*Notification to 1*. On an iPhone, add the app to the Home Screen first.

**The phone app** (`mobile/`, PLAN.md §17) needs nothing extra on the server:
it uses the same API, and its live updates go through Caddy at
`/api/v1/m/ws` (already in `deploy/Caddyfile`). Its notifications use the
same `PUSH_PROVIDER=webpush` switch; they go through Expo's push service, so
the server must reach `exp.host` (it does, unless outbound traffic is
blocked). `EXPO_ACCESS_TOKEN` is needed only if Expo's "enhanced push
security" is turned on for the project. A test `.apk` for the pilot gyms'
members is built against this server with
`EXPO_PUBLIC_API_URL=https://app.gymbhai.com make apk` (`docs/MOBILE.md` §4).
`MASTER_OTP` must be gone before members install it: with a real SMS gateway,
the app signs in like the web.

## 6. Updating

```sh
git pull
$C up -d --build
```

Migrations run on start. Before any update that adds a migration, take a
backup by hand (`$C exec backup backup.sh`).

## 7. Looking after it

| Check | Where |
|---|---|
| Is it up? | The uptime check on `/health/ready` |
| Errors | Sentry (if `SENTRY_DSN` is set), or `$C logs --tail 200 api worker` |
| SMS failing | Staff dashboard → SMS; `$C logs worker` |
| Backups | `$C exec backup su-exec postgres pgbackrest info`: a full backup each week, a differential each night, WAL up to the last minute; `/db` gains one dump a night |
| Archiving | `$C exec db psql -U "$POSTGRES_USER" -c "select * from pg_stat_archiver"`: `failed_count` not rising. While R2 is unreachable, WAL waits in the database's volume, so watch the disk |
| Disk | `df -h`; `docker system prune` removes old images |

Never run `alembic downgrade` against the live database: rolling back drops
tables. `make migration-check` does its round trip in a scratch database.

## 8. Disaster: put the database back as it was at a moment

Someone deleted what they shouldn't have, or the data is damaged. Everything
written after the moment you choose is lost, so look first with
`restore-to-time.sh` (§4) and pick the latest moment that is still right.

```sh
$C stop api worker web backup db
$C run --rm --no-deps --entrypoint restore-live.sh db "2026-10-17 14:05:00+05:45"
$C up -d
$C exec backup base-backup.sh full
```

The new full backup starts the history afresh from the restored database.

**If the server itself is gone:** set up a new one (§1–2) with the same
`.env.prod`, and restore *before* the first start, so the database is never
created empty:

```sh
$C build
$C run --rm --no-deps --entrypoint restore-live.sh db latest
$C up -d
$C exec backup base-backup.sh full
```

`latest` replays everything the archive has: about the last minute before
the old server stopped is all that can be lost.
