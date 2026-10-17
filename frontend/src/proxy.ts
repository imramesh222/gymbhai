import { NextResponse, type NextRequest } from "next/server";

import { contentSecurityPolicy, newNonce } from "@/lib/csp";

/**
 * A Content-Security-Policy with a fresh nonce on every page (src/lib/csp.ts).
 * Next.js reads the nonce from the request's header and puts it on its own
 * scripts, so pages are rendered per request (see the root layout).
 */
export function proxy(request: NextRequest) {
  const nonce = newNonce();
  const policy = contentSecurityPolicy(nonce, process.env.NODE_ENV === "development");

  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", policy);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", policy);
  return response;
}

export const config = {
  matcher: [
    {
      // Pages only: not the API (JSON, behind its own headers in Caddy), not
      // built assets, icons or the service worker, and not link prefetches.
      source: "/((?!api|_next/static|_next/image|favicon.ico|sw.js|.*\\.png$).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
