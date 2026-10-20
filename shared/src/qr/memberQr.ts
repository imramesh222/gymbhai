/**
 * The member's changing QR code (PLAN.md §4.2) — the same computation as
 * backend/app/core/qr.py:  gb1.<member hex>.<30-second window>.<signature>
 *
 * Runs entirely on the phone from the key handed over at sign-in, so it works
 * with no mobile data; only the scanner needs the internet.
 *
 * gb2 (§19.2) is the same code signed with Ed25519, which a kiosk can check
 * offline from a public key but never make. Ed25519 comes from each app's own
 * @noble/ed25519, passed in as `sign` and `verify`: shared/ has no packages.
 */
import { base64Url, fromBase64Url, hmacSha256, utf8 } from "./hmac";

export interface QrIdentity {
  member_hex: string;
  key: string;
  version: number;
  window_seconds: number;
  /** Ed25519, for gb2 (§19.2). Missing from a copy saved before gb2. */
  signing_key?: string | null;
}

/** Ed25519 from the app: sign with a 32-byte key, check with a public key. */
export type Sign = (message: Uint8Array, secretKey: Uint8Array) => Uint8Array;
export type Verify = (
  signature: Uint8Array,
  message: Uint8Array,
  publicKey: Uint8Array,
) => boolean;

const SIGNATURE_CHARS = 16;

export function windowAt(unixMs: number, windowSeconds = 30): number {
  return Math.floor(unixMs / 1000 / windowSeconds);
}

export function signature(
  key: string,
  memberHex: string,
  window: number,
): string {
  const digest = hmacSha256(fromBase64Url(key), utf8(`${memberHex}.${window}`));
  return base64Url(digest).slice(0, SIGNATURE_CHARS);
}

export function memberCode(
  identity: QrIdentity,
  unixMs: number = Date.now(),
  sign?: Sign,
): string {
  const window = windowAt(unixMs, identity.window_seconds);
  if (identity.signing_key && sign) {
    const signed = sign(
      utf8(`${identity.member_hex}.${window}`),
      fromBase64Url(identity.signing_key),
    );
    return `gb2.${identity.member_hex}.${window}.${base64Url(signed)}`;
  }
  return `gb1.${identity.member_hex}.${window}.${signature(identity.key, identity.member_hex, window)}`;
}

export interface Scanned {
  kind: "app" | "app2" | "card";
  member_hex?: string;
  window?: number;
  signature?: string;
  card_token?: string;
}

/** What a scanned string claims to be; null if it isn't one of ours. */
export function parseCode(code: string): Scanned | null {
  const text = code.trim();
  if (text.startsWith("gbc.")) {
    const token = text.slice(4);
    return token.length >= 8 && token.length <= 64
      ? { kind: "card", card_token: token }
      : null;
  }
  const parts = text.split(".");
  if (parts.length !== 4 || (parts[0] !== "gb1" && parts[0] !== "gb2"))
    return null;
  const memberHex = parts[1].toLowerCase();
  if (!/^[0-9a-f]{32}$/.test(memberHex) || !/^\d+$/.test(parts[2])) return null;
  return {
    kind: parts[0] === "gb1" ? "app" : "app2",
    member_hex: memberHex,
    window: Number(parts[2]),
    signature: parts[3],
  };
}

/** A gb2 code, checked offline against the member's public key (§19.2):
 * this window or one either side, as the server allows. */
export function verifyCode2(
  scanned: Scanned,
  publicKey: string,
  verify: Verify,
  unixMs: number = Date.now(),
  windowSeconds = 30,
): boolean {
  if (scanned.kind !== "app2" || scanned.window === undefined) return false;
  if (Math.abs(scanned.window - windowAt(unixMs, windowSeconds)) > 1)
    return false;
  try {
    return verify(
      fromBase64Url(scanned.signature ?? ""),
      utf8(`${scanned.member_hex}.${scanned.window}`),
      fromBase64Url(publicKey),
    );
  } catch {
    return false;
  }
}

/** Milliseconds until the code changes, for the countdown under it. */
export function msUntilNext(
  identity: QrIdentity,
  unixMs: number = Date.now(),
): number {
  const period = identity.window_seconds * 1000;
  return period - (unixMs % period);
}
