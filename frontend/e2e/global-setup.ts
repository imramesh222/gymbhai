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
  "/staff/login",
  "/staff",
  "/staff/members",
  "/staff/members/new",
  "/staff/members/00000000-0000-0000-0000-000000000000",
  "/staff/members/00000000-0000-0000-0000-000000000000/renew",
  "/staff/members/00000000-0000-0000-0000-000000000000/card",
  "/staff/memberships/00000000-0000-0000-0000-000000000000",
  "/staff/receipts/00000000-0000-0000-0000-000000000000",
  "/staff/expiring",
  "/staff/door",
  "/staff/payment-requests",
  "/staff/payments",
  "/staff/attendance",
  "/staff/reports",
  "/staff/notices",
  "/staff/sms",
  "/staff/team",
  "/staff/data",
  "/staff/subscription",
  "/staff/settings",
  "/staff/settings/poster",
  "/staff/profile",
  "/kiosk",
  "/admin",
  "/admin/plans",
  "/warm-up-gym",
  "/warm-up-gym/renew",
  "/warm-up-gym/payments",
  "/warm-up-gym/visits",
  "/warm-up-gym/notices",
  "/warm-up-gym/profile",
];

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
}
