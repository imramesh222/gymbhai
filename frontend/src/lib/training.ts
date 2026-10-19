/**
 * Personal training (PLAN.md §18.3), as the staff screens describe it.
 */
import { plural, t } from "@/i18n";

import type { PtPackage } from "./api";

/** "8 of 12 sessions left" for a pack; "5 sessions so far" for monthly. */
export function sessionsLine(
  pkg: Pick<PtPackage, "sessions" | "sessions_left" | "sessions_used">,
): string {
  if (pkg.sessions === null)
    return plural(pkg.sessions_used, "pt.sessionsSoFar.one", "pt.sessionsSoFar.other");
  return t("pt.sessionsLeft", { left: pkg.sessions_left ?? 0, total: pkg.sessions });
}

/**
 * Whether someone may record (or void) a session on it now: its own trainer,
 * or staff who sell personal training, while it's under way. The server
 * checks the same.
 */
export function mayRecord(
  pkg: Pick<PtPackage, "trainer_id" | "status">,
  staffId: string | undefined,
  can: (permission: string) => boolean,
): boolean {
  if (pkg.status !== "active") return false;
  return mayCorrect(pkg, staffId, can);
}

/** Voiding a session: the same people, whatever the package's status now. */
export function mayCorrect(
  pkg: Pick<PtPackage, "trainer_id">,
  staffId: string | undefined,
  can: (permission: string) => boolean,
): boolean {
  if (can("pt.sell")) return true;
  return can("pt.train") && staffId !== undefined && pkg.trainer_id === staffId;
}
