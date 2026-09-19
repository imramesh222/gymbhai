/**
 * The member's changing QR code (PLAN.md §4.2) — the same computation as
 * backend/app/core/qr.py:  gb1.<member hex>.<30-second window>.<signature>
 *
 * Runs entirely on the phone from the key handed over at sign-in, so it works
 * with no mobile data; only the scanner needs the internet.
 */
import { base64Url, fromBase64Url, hmacSha256, utf8 } from "./hmac";

export interface QrIdentity {
  member_hex: string;
  key: string;
  version: number;
  window_seconds: number;
}

const SIGNATURE_CHARS = 16;

export function windowAt(unixMs: number, windowSeconds = 30): number {
  return Math.floor(unixMs / 1000 / windowSeconds);
}

export function signature(key: string, memberHex: string, window: number): string {
  const digest = hmacSha256(fromBase64Url(key), utf8(`${memberHex}.${window}`));
  return base64Url(digest).slice(0, SIGNATURE_CHARS);
}

export function memberCode(identity: QrIdentity, unixMs: number = Date.now()): string {
  const window = windowAt(unixMs, identity.window_seconds);
  return `gb1.${identity.member_hex}.${window}.${signature(identity.key, identity.member_hex, window)}`;
}

/** Milliseconds until the code changes, for the countdown under it. */
export function msUntilNext(identity: QrIdentity, unixMs: number = Date.now()): number {
  const period = identity.window_seconds * 1000;
  return period - (unixMs % period);
}
