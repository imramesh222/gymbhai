import { ADMIN_EMAIL, ADMIN_PASSWORD, totp } from "./helpers";

/**
 * Visit every route once, one at a time, before the tests start.
 *
 * A Next.js dev server compiles each route on its first request. Twenty-odd
 * routes compiling at once under parallel tests starve the server — even a
 * static file then takes 20 s — and tests time out for no fault of the app.
 * Against a production build (as in CI) this is a quick no-op.
 */
const ROUTES = [
  "/",
  "/signup",
  "/terms",
  "/privacy",
  "/staff/login",
  "/staff/forgot",
  "/staff/two-step",
  "/staff",
  "/staff/members",
  "/staff/members/new",
  "/staff/members/00000000-0000-0000-0000-000000000000",
  "/staff/members/00000000-0000-0000-0000-000000000000/renew",
  "/staff/members/00000000-0000-0000-0000-000000000000/card",
  "/staff/memberships/00000000-0000-0000-0000-000000000000",
  "/staff/receipts/00000000-0000-0000-0000-000000000000",
  "/staff/enquiries",
  "/staff/follow-up",
  "/staff/door",
  "/staff/payment-requests",
  "/staff/freeze-requests",
  "/staff/payments",
  "/staff/attendance",
  "/staff/reports",
  "/staff/notices",
  "/staff/automations",
  "/staff/sms",
  "/staff/team",
  "/staff/data",
  "/staff/subscription",
  "/staff/help",
  "/staff/whats-new",
  "/staff/settings",
  "/staff/settings/plans",
  "/staff/settings/payment-accounts",
  "/staff/settings/branches",
  "/staff/settings/check-in",
  "/staff/settings/door",
  "/staff/settings/security",
  "/staff/settings/poster",
  "/staff/profile",
  "/kiosk",
  "/admin",
  "/admin/plans",
  "/admin/changelog",
  "/admin/referrals",
  "/admin/account",
  "/warm-up-gym",
  "/warm-up-gym/renew",
  "/warm-up-gym/payments",
  "/warm-up-gym/visits",
  "/warm-up-gym/notices",
  "/warm-up-gym/profile",
];

/**
 * Platform admins must use two-step sign-in (PLAN.md §16.1). The e2e admin is
 * reset before each run (scripts/create_platform_admin.py turns it off), so
 * turn it on here, once, and hand the recovery codes to the tests through the
 * environment: codes from the app work once each, and parallel tests would
 * race for them.
 */
async function setUpAdminTwoStep(base: string) {
  const post = (path: string, body: unknown, token?: string) =>
    fetch(base + path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    }).then(async (response) => ({ ok: response.ok, body: await response.json() }));

  const login = await post("/api/v1/auth/login", {
    identifier: ADMIN_EMAIL,
    password: ADMIN_PASSWORD,
  });
  if (!login.ok || !login.body.access_token) {
    console.warn(
      "e2e admin: no plain sign-in (missing, or two-step already on). " +
        "Reset it with scripts.create_platform_admin; admin tests will fail.",
    );
    return;
  }
  const token = login.body.access_token as string;
  const setup = await post(
    "/api/v1/auth/two-step/setup",
    { password: ADMIN_PASSWORD },
    token,
  );
  const enabled = await post(
    "/api/v1/auth/two-step/enable",
    { code: totp(setup.body.secret) },
    token,
  );
  process.env.E2E_ADMIN_RECOVERY_CODES = JSON.stringify(enabled.body.recovery_codes);
}

export default async function globalSetup() {
  const base = process.env.E2E_BASE_URL ?? "http://localhost:3000";
  if (process.env.E2E_IGNORE_HTTPS) process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";
  for (const route of ROUTES) {
    try {
      await fetch(base + route, { signal: AbortSignal.timeout(120_000) });
    } catch {
      // A route that fails here will fail its own test, with a clearer error.
    }
  }
  await setUpAdminTwoStep(base);
}
