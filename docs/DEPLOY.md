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
start with the development one), the S3 keys and buckets, and the domains.

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

## 4. Backups — test a restore before the first real gym

Backups run at 02:00 Nepal time. Run one now, and restore it into a scratch
database to prove it works (PLAN.md §11):

```sh
C="docker compose -f docker-compose.prod.yml --env-file .env.prod"
$C exec backup backup.sh
$C exec backup sh -c 'aws s3 --endpoint-url "$S3_ENDPOINT_URL" ls "s3://$BACKUP_BUCKET/db/"'
$C exec backup restore.sh gymbhai-<stamp>.dump gymbhai_restore_test
$C exec db dropdb -U GymBhai gymbhai_restore_test
```

The restore prints the number of gyms and members it found.

## 5. SMS and email, live

The Sparrow and Aakash adapters follow those gateways' published APIs but
have not been run against a live account. Before switching:

1. Set `SMS_PROVIDER=sparrow` (or `aakash`) and its token in `.env.prod`.
2. Restart: `$C up -d api worker`.
3. Sign up a test gym with your own phone, add yourself as a member, and
   check the welcome SMS arrives. Then sign in to the member app with the code.
4. Check the SMS log in the staff dashboard shows it as **Sent**.

Do the same for email with `EMAIL_PROVIDER=smtp`, using a member with an email.

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
| Backups | The bucket should gain one file a night; 30 days are kept |
| Disk | `df -h`; `docker system prune` removes old images |

Never run `alembic downgrade` against the live database: rolling back drops
tables. `make migration-check` does its round trip in a scratch database.
