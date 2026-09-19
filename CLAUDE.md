# GymBhai

Multi-tenant gym membership software for gyms in Nepal: one product, many gyms. Gyms manage members, plans, payments and check-ins; members get an installable web app with their membership and a personal QR code.

**[PLAN.md](PLAN.md) is the source of truth** for scope, data model, screens, API and build order (M0–M5). Read the relevant section before building a feature, and update PLAN.md when a decision changes.

## Stack

- Backend: FastAPI (Python 3.13), SQLAlchemy 2, Alembic, Pydantic 2 — `backend/`
- Frontend: Next.js (App Router), TypeScript, Tailwind CSS — `frontend/`
- Database: PostgreSQL 16
- Everything runs in Docker containers via Docker Compose: `db`, `api`, `worker`, `web`
- Tests: pytest, Vitest + Testing Library, Playwright

## Rules that are easy to break

- **Tenancy:** every gym-owned table has `gym_id`; the gym always comes from the signed-in user's token, never the request body. Cross-gym access must return 404, and a regression test proves it.
- **Permissions, not roles:** the owner has everything; staff get individually ticked permissions and branches (PLAN.md §2.1). Every endpoint checks a specific permission.
- **Money never passes through us.** Members pay gyms directly (cash or the gym's own eSewa/Khalti/Fonepay/bank QR); we only record payments. Money is stored as integer paisa.
- **Membership status is computed from dates**, never stored. Renewals are new rows; nothing is overwritten — every edit goes to `activity_log` with before/after.
- **Dates:** stored in AD; each gym chooses AD or BS for counting plan months and AD/BS/both for display. Time zone Asia/Kathmandu.
- **English only at launch**, but all UI text goes through translation files so Nepali can be added later.
- **SMS** goes through a provider interface (`console` in development; Sparrow and Aakash adapters). No provider is chosen yet.
- **Pricing** of our plans lives in the database, edited from `/admin` — never hard-coded.
- Check-in is source-agnostic so fingerprint/face readers can be added later.

## Owner

Ramesh Rawat. Previous project with the same stack and patterns (tenancy, tests, Docker setup): `~/namaste-desk`.
