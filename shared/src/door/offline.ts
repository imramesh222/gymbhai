/**
 * The door's rules with no internet (PLAN.md §19.2): what a kiosk decides from
 * its roster when it can't ask the server. The roster's letters, one a day,
 * already carry the server's rules for each day (backend/app/services/
 * kiosk.py); here are the rest: the hour, money owed, visits used since the
 * roster came, and the re-scan window. offline.test.ts and the server's
 * tests/integration/test_offline_kiosk.py check the same cases.
 */
import type { AccessWindow } from "../accessHours";

export interface RosterMember {
  id: string;
  name: string;
  code: string;
  photo: string | null;
  photo_url: string | null;
  /** SHA-256 of their card's token, hex. */
  card: string;
  /** Their gb2 public key. */
  key: string;
  /** One letter a day from the roster's from_date. */
  days: string;
  hours: AccessWindow[] | null;
  visits_left: number | null;
  owes: boolean;
  plan_name: string | null;
  valid_until: string | null;
}

export interface KioskRules {
  grace_days: number;
  rescan_minutes: number;
  dues_rule: "allow" | "warn" | "refuse";
}

export interface Roster {
  branch_id: string;
  from_date: string;
  server_time: string;
  offline_days: number;
  rules: KioskRules;
  members: RosterMember[];
}

export type OfflineResult =
  | "allowed"
  | "warned"
  | "duplicate"
  | "denied_expired"
  | "denied_frozen"
  | "denied_branch"
  | "denied_dues"
  | "denied_visits_used"
  | "denied_hours";

export interface Decision {
  result: OfflineResult;
  reason: string | null;
  let_in: boolean;
}

const NEPAL_OFFSET_MS = (5 * 60 + 45) * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;

/** The day, weekday (0 is Monday) and "HH:MM" in Nepal: +05:45, no DST. */
export function inNepal(unixMs: number): {
  date: string;
  weekday: number;
  time: string;
} {
  const local = new Date(unixMs + NEPAL_OFFSET_MS);
  return {
    date: local.toISOString().slice(0, 10),
    weekday: (local.getUTCDay() + 6) % 7,
    time: local.toISOString().slice(11, 16),
  };
}

/** Like backend/app/services/checkins.py `within_hours`. */
export function withinHours(
  hours: AccessWindow[] | null,
  unixMs: number,
): boolean {
  if (!hours || hours.length === 0) return true;
  const { weekday, time } = inNepal(unixMs);
  return hours.some(
    (w) => w.days.includes(weekday) && w.from <= time && time < w.to,
  );
}

function dayIndex(fromDate: string, date: string): number {
  return Math.round(
    (Date.parse(`${date}T00:00:00Z`) - Date.parse(`${fromDate}T00:00:00Z`)) /
      DAY_MS,
  );
}

const LET_IN: OfflineResult[] = ["allowed", "warned"];

/**
 * `usedOffline`: visits this kiosk let them in since the roster came;
 * `lastLetIn`: when it last let them in, for the re-scan window.
 */
export function decideOffline(
  member: RosterMember,
  roster: Pick<Roster, "from_date" | "rules">,
  unixMs: number,
  usedOffline = 0,
  lastLetIn: number | null = null,
): Decision {
  const index = dayIndex(roster.from_date, inNepal(unixMs).date);
  const letter =
    index >= 0 && index < member.days.length ? member.days[index] : "x";
  let result: OfflineResult;
  let reason: string | null = null;
  switch (letter) {
    case "f":
      [result, reason] = ["denied_frozen", "frozen"];
      break;
    case "v":
      [result, reason] = ["denied_visits_used", "visits_used"];
      break;
    case "g":
      [result, reason] = ["warned", "expired_grace"];
      break;
    case "b":
      [result, reason] = ["denied_branch", "branch"];
      break;
    case "a":
      if (
        member.visits_left !== null &&
        member.visits_left - usedOffline <= 0
      ) {
        [result, reason] = ["denied_visits_used", "visits_used"];
      } else if (!withinHours(member.hours, unixMs)) {
        [result, reason] = ["denied_hours", "hours"];
      } else if (member.owes && roster.rules.dues_rule === "refuse") {
        [result, reason] = ["denied_dues", "dues"];
      } else if (member.owes && roster.rules.dues_rule === "warn") {
        [result, reason] = ["warned", "dues"];
      } else {
        result = "allowed";
      }
      break;
    default:
      [result, reason] = ["denied_expired", "expired"];
  }
  if (
    LET_IN.includes(result) &&
    roster.rules.rescan_minutes > 0 &&
    lastLetIn !== null &&
    unixMs - lastLetIn <= roster.rules.rescan_minutes * 60 * 1000
  ) {
    result = "duplicate";
  }
  return {
    result,
    reason,
    let_in: LET_IN.includes(result) || result === "duplicate",
  };
}
