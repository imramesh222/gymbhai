# Commands

The commands used most often in development, in one place. Run them from
`~/gymbahi` unless a block says otherwise. More detail: `docs/LOCAL.md`
(start, stop, new Wi-Fi) and `docs/MOBILE.md` (the phone app). `make help`
lists every `make` command.

## Start and stop

```sh
make up            # database, API, worker and web dashboard (Docker); rebuilds images first
docker compose up -d   # the same, with the images already built: no rebuild
make down          # stop everything; the data stays
make ps            # what is running
make logs          # follow the logs (Ctrl+C to stop following)
```

The code is mounted into the containers, so code changes need no rebuild.
Use `make up` after a change to `backend/requirements*.txt`,
`frontend/package.json`, `frontend/package-lock.json` or a `Dockerfile`.

## Reset the development database

Drops only the `gymbhai` dev database. The test databases in the same
Postgres (pytest's, the e2e one) are not touched.

```sh
# 1. Stop everything connected to the database
docker compose stop api worker web

# 2. Drop the database and create it again (FORCE closes connections still open)
docker compose exec db psql -U gymbhai -d postgres \
  -c 'DROP DATABASE gymbhai WITH (FORCE)' \
  -c 'CREATE DATABASE gymbhai'

# 3. Run the migrations
make migrate

# 4. Start everything again
docker compose up -d
```

The `api` container also runs `alembic upgrade head` each time it starts, so
step 4 alone would migrate too; step 3 shows any error directly.

The database is then empty, apart from what the migrations seed (our platform
plans). To make it usable again:

```sh
make admin name="Ramesh" email=you@example.com   # your /admin login; asks for a password
make seed-demo                                    # the /demo gym with a year of data
make seed-app                                     # the /e2e-app gym for phone app tests
```

Afterwards, sign in again in the browser and on the phone: old sign-ins point
to users that no longer exist.

## Migrations

```sh
make migrate                         # apply migrations
make migration m="add members"       # a new migration from model changes
make migration-check                 # apply, compare with models, roll back: in a scratch database
```

## Sign-ins after seeding

| | |
|---|---|
| Demo gym owner (`make seed-demo`) | `9800000200`, password `demo-password-123` |
| Test gym owner (`make seed-app`) | `9800000100`, password `app-test-password-123` |
| Member sign-in code | `MASTER_OTP` from `.env` |

## Tests

```sh
make db              # Postgres must be running for pytest
make test            # pytest, Vitest and the phone app's Jest
make test-backend    # pytest only
make lint            # ruff, eslint, tsc
make fmt             # format backend and frontend
make e2e             # Playwright on its own database and stack
make e2e-mobile app=com.gymbhai.member   # Maestro flows on the running emulator, installed app
```

- Use `make e2e`, never `make e2e-dev`: the dev stack writes to the dev
  database and sends real email through the Gmail settings in `.env`.
- Don't run `make e2e` and pytest at the same time.

## Database shell

```sh
make psql            # psql into the dev database
make shell           # bash in the api container
```

## Phone app

```sh
make mobile-env      # point the app at this Mac's Wi-Fi address (after changing Wi-Fi)
cd mobile
npx expo start       # dev server; the development build loads code from here
```

**EAS Update** (new JavaScript reaches installed apps, no reinstall):

```sh
cd mobile
EXPO_PUBLIC_API_URL=https://app.gymbhai.com npx eas-cli update --channel preview --message "..."
npx eas-cli update --channel production --message "..."   # after publishing
npx eas-cli update:list                                   # what was sent
npx eas-cli update:republish --group <id>                 # roll back
```

**EAS Build** (a new app to install; uses the monthly build quota):

```sh
cd mobile
npx eas-cli build -p android --profile development   # development build on your phone
npx eas-cli build -p android --profile preview       # tester .apk
npx eas-cli build -p android --profile production    # Play Store .aab
npx eas-cli build:list                               # builds and their links
```

Which one a change needs:

| Changed | Needs |
|---|---|
| `mobile/src/`, `shared/src/` (screens, strings, types, dates) | EAS Update; the development build needs nothing |
| `mobile/package.json` packages with native code (`expo-*`, `react-native-*`), an Expo SDK upgrade | EAS Build |
| `mobile/app.config.ts` name, id, scheme, icon, splash, permissions, plugins, app links | EAS Build |
| `mobile/assets/` icons and splash, `google-services.json`, `eas.json`, `mobile/brands/` | EAS Build |
| `backend/`, `frontend/`, `docs/` | Neither |

After a native change, bump `version` in `mobile/app.config.ts`. Updates only
reach builds with the same version, so old builds don't get JavaScript their
native code can't run.
