/**
 * The kiosk with no internet (PLAN.md §19.2): the roster it keeps, the scans
 * waiting to be sent, and deciding a scan from them. The rules themselves are
 * shared (@shared/door/offline) and checked against the server's door.
 *
 * Kept in this browser's own storage. Without it (a private window) the
 * kiosk works online only, as before.
 */
import {
  decideOffline,
  inNepal,
  type Roster,
  type RosterMember,
} from "@shared/door/offline";
import { sha256, toHex, utf8 } from "@shared/qr/hmac";
import { parseCode, verifyCode2 } from "@shared/qr/memberQr";

import type { ScanResult } from "@/lib/api";
import { daysBetween } from "@/lib/dates";
import { verify } from "@/lib/ed25519";

const ROSTER_KEY = "gymbhai.kiosk.roster";
const QUEUE_KEY = "gymbhai.kiosk.queue";
const DAY_MS = 24 * 60 * 60 * 1000;

export interface StoredRoster {
  roster: Roster;
  /** Our clock minus this device's, so offline it keeps the server's time. */
  offset: number;
}

export interface QueuedScan {
  client_id: string;
  member_id: string;
  method: "app_qr" | "card_qr";
  at: string;
  result: string;
}

function read<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function write(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Full or blocked: the kiosk still works online.
  }
}

export function storedRoster(): StoredRoster | null {
  return read<StoredRoster>(ROSTER_KEY);
}

export function keepRoster(
  roster: Roster,
  deviceNow: number = Date.now(),
): StoredRoster {
  const stored = { roster, offset: Date.parse(roster.server_time) - deviceNow };
  write(ROSTER_KEY, stored);
  return stored;
}

/** A revoked kiosk keeps nothing about members. */
export function forgetEverything(): void {
  try {
    localStorage.removeItem(ROSTER_KEY);
    localStorage.removeItem(QUEUE_KEY);
  } catch {
    // Nothing kept.
  }
}

export function waiting(): QueuedScan[] {
  return read<QueuedScan[]>(QUEUE_KEY) ?? [];
}

export function markSent(ids: string[]): void {
  const done = new Set(ids);
  write(
    QUEUE_KEY,
    waiting().filter((s) => !done.has(s.client_id)),
  );
}

export function serverNow(
  stored: StoredRoster,
  deviceNow: number = Date.now(),
): number {
  return deviceNow + stored.offset;
}

export function tooOld(stored: StoredRoster, deviceNow: number = Date.now()): boolean {
  const age = serverNow(stored, deviceNow) - Date.parse(stored.roster.server_time);
  return age > stored.roster.offline_days * DAY_MS;
}

function newId(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return toHex(bytes);
}

function blank(result: string, reason: string | null): ScanResult {
  return {
    result,
    let_in: false,
    reason,
    check_in_id: null,
    member_id: null,
    member_name: null,
    member_code: null,
    photo_url: null,
    plan_name: null,
    days_left: 0,
    valid_until: null,
    dues: 0,
    visits_left: null,
    can_override: false,
  };
}

function find(
  code: string,
  roster: Roster,
  now: number,
): { member: RosterMember; method: QueuedScan["method"] } | ScanResult {
  const scanned = parseCode(code);
  if (!scanned) return blank("unknown", "unknown_code");
  if (scanned.kind === "card") {
    const hash = toHex(sha256(utf8(scanned.card_token ?? "")));
    const member = roster.members.find((m) => m.card === hash);
    return member ? { member, method: "card_qr" } : blank("unknown", "unknown_code");
  }
  // An app too old for gb2 signs with a key only the server can check.
  if (scanned.kind === "app") return blank("denied_offline", "needs_internet");
  const member = roster.members.find(
    (m) => m.id.replaceAll("-", "") === scanned.member_hex,
  );
  if (!member || !verifyCode2(scanned, member.key, verify, now))
    return blank("unknown", "unknown_code");
  return { member, method: "app_qr" };
}

/**
 * A scan decided here, as the card shows it, and kept to send later (none for
 * a code it can't read). Visits let in since the roster came count against a
 * pack and the re-scan window: they are the scans still waiting.
 */
export function decide(
  code: string,
  stored: StoredRoster,
  deviceNow: number = Date.now(),
): { result: ScanResult; queued: QueuedScan | null } {
  if (tooOld(stored, deviceNow))
    return { result: blank("denied_offline", "offline_too_long"), queued: null };
  const now = serverNow(stored, deviceNow);
  const found = find(code, stored.roster, now);
  if (!("member" in found)) return { result: found, queued: null };
  const { member, method } = found;

  const mine = waiting().filter(
    (s) =>
      s.member_id === member.id && (s.result === "allowed" || s.result === "warned"),
  );
  const last = mine.length ? Math.max(...mine.map((s) => Date.parse(s.at))) : null;
  const decision = decideOffline(member, stored.roster, now, mine.length, last);

  const queued: QueuedScan = {
    client_id: newId(),
    member_id: member.id,
    method,
    at: new Date(now).toISOString(),
    result: decision.result,
  };
  write(QUEUE_KEY, [...waiting(), queued]);

  const counted = decision.result === "allowed" || decision.result === "warned";
  return {
    queued,
    result: {
      ...blank(decision.result, decision.reason),
      let_in: decision.let_in,
      member_id: member.id,
      member_name: member.name,
      member_code: member.code,
      photo_url: member.photo_url,
      plan_name: member.plan_name,
      valid_until: member.valid_until,
      days_left: member.valid_until
        ? Math.max(daysBetween(inNepal(now).date, member.valid_until) + 1, 0)
        : 0,
      visits_left:
        member.visits_left === null
          ? null
          : Math.max(member.visits_left - mine.length - (counted ? 1 : 0), 0),
    },
  };
}
