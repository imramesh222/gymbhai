/**
 * The QR staff show at the desk to sign a member in with no SMS code
 * (PLAN.md §18.4): the gym's address with a one-time token after "#desk=",
 * as in https://app.gymbhai.com/fitness-zone#desk=Q2x… . The token rides in
 * the fragment, which a browser never sends, so no server or log sees it.
 *
 * Read by hand rather than with URLSearchParams, which React Native's
 * runtime only half implements.
 */
const TOKEN = /(?:^|[#&])desk=([A-Za-z0-9_-]{16,64})(?:&|$)/;

/** The one-time token in a desk QR's link, or null for any other link. */
export function deskToken(link: string): string | null {
  const at = link.indexOf("#");
  if (at < 0) return null;
  return TOKEN.exec(link.slice(at))?.[1] ?? null;
}
