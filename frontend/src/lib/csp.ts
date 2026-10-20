/**
 * The Content-Security-Policy every page is sent with (PLAN.md §11, §16.1).
 *
 * Scripts run only with this request's nonce (src/proxy.ts), and whatever
 * those load ('strict-dynamic'): an injected <script> or onclick= never runs.
 * Inline styles stay allowed: React renders style={...} as attributes on the
 * server, and those can't carry a nonce. Everything else comes from our own
 * origin, which includes the API, member photos (signed /api/v1/files links)
 * and the live-update stream. Forms post to us, or to eSewa for a member's
 * payment. Nobody may put our pages in a frame.
 */
export function contentSecurityPolicy(nonce: string, dev: boolean): string {
  const directives = [
    "default-src 'self'",
    // React's development build uses eval for its error overlays; production never.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' blob: data:",
    "font-src 'self'",
    // Development reloads pages over a websocket to the dev server.
    `connect-src 'self'${dev ? " ws: wss:" : ""}`,
    // The member app's service worker; 'strict-dynamic' would ignore 'self'.
    "worker-src 'self'",
    "manifest-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    // eSewa's checkout is a signed form posted to eSewa (PLAN.md §20.2).
    "form-action 'self' https://epay.esewa.com.np https://rc-epay.esewa.com.np",
    "frame-ancestors 'none'",
  ];
  return directives.join("; ");
}

/** A fresh nonce for each page request. */
export function newNonce(): string {
  return btoa(crypto.randomUUID());
}
