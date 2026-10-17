/**
 * Where the API is. Production by default; in development the Mac's LAN
 * address, e.g. EXPO_PUBLIC_API_URL=http://192.168.1.20:8001 in mobile/.env
 * (README.md). The app talks to the API directly, not through Next.js.
 */
export const API_URL = (
  process.env.EXPO_PUBLIC_API_URL ?? "https://app.gymbhai.com"
).replace(/\/+$/, "");

/** The member app's WebSocket (PLAN.md §17.3). */
export const SOCKET_URL = `${API_URL.replace(/^http/, "ws")}/api/v1/m/ws`;

/** The domain on gym posters and in the welcome SMS. */
export const APP_DOMAIN = "app.gymbhai.com";

/** The brand colour before a gym's own is known. */
export const DEFAULT_BRAND = "#1d5fd1";

/**
 * An image the API gave as a path ("/api/v1/files/..."), or a link made for
 * browsers on another host (receipts): fetched from the API we talk to.
 */
export function apiUrl(pathOrUrl: string): string {
  if (pathOrUrl.startsWith("/")) return API_URL + pathOrUrl;
  const match = /^https?:\/\/[^/]+(\/api\/.*)$/.exec(pathOrUrl);
  return match ? API_URL + match[1] : pathOrUrl;
}
