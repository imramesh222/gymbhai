# GymBahi

Gym membership software for gyms in Nepal: members, plans, payments, renewals
and QR check-ins, with an installable member app. One product, many gyms.

- **[PLAN.md](PLAN.md)** — scope, data model, screens, API and build order
- **[CLAUDE.md](CLAUDE.md)** — the rules that are easy to break

## Run it

Needs Docker, Python 3.13 and Node 24.

```sh
make setup   # .env, dependencies, database, migrations
make up      # db, api, worker, web in Docker
```

- Web: http://localhost:3000 — sign up a gym at `/signup`
- API docs: http://localhost:8000/docs (`API_PORT` in `.env`)

`make help` lists everything else.

## Tests

```sh
make test    # pytest (needs `make db`) + Vitest
make e2e     # Playwright against the running stack
make lint
```

Backend tests run against a separate `gymbahi_test` database, created on first
run. `tests/regression` holds the rules that must never break: tenant isolation,
a permission check on every route, and `gym_id` on every gym-owned table.

## Layout

```
backend/    FastAPI app, worker, Alembic migrations, pytest
frontend/   Next.js app: staff dashboard, member app, kiosk, admin
```

The browser only talks to the Next.js server; it forwards `/api/*` to FastAPI
(`frontend/next.config.ts`), so the refresh cookie is first-party and there is
no CORS to configure.
# gymbhai
