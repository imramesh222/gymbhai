import type { MessageKey } from "@/i18n";
import { plural, t } from "@/i18n";
import type { Trigger } from "@/lib/api";

/** What each automation's `days` means, and what it may say (PLAN.md §16.3, 8.2). */
export interface TriggerInfo {
  trigger: Trigger;
  /** Memberships', personal training's (§18.3) or progress's (§19.5): each
   * under its own heading. */
  group: "membership" | "pt" | "progress";
  title: MessageKey;
  help: MessageKey;
  min: number;
  max: number;
  /** The placeholders a message for this trigger can fill in. */
  placeholders: string[];
  /** A starting wording for a new one. */
  example: MessageKey;
  /** Sent by push only, free: no SMS count to show (§19.5). */
  pushOnly?: boolean;
}

const COMMON = ["name", "gym", "link", "code"];

export const TRIGGERS: TriggerInfo[] = [
  {
    trigger: "expiry",
    group: "membership",
    title: "automations.expiry.title",
    help: "automations.expiry.help",
    min: -60,
    max: 60,
    placeholders: [...COMMON, "plan", "end_date", "days"],
    example: "automations.expiry.example",
  },
  {
    trigger: "lapsed",
    group: "membership",
    title: "automations.lapsed.title",
    help: "automations.lapsed.help",
    min: 1,
    max: 365,
    placeholders: [...COMMON, "plan", "end_date", "days"],
    example: "automations.lapsed.example",
  },
  {
    trigger: "dues",
    group: "membership",
    title: "automations.dues.title",
    help: "automations.dues.help",
    min: 1,
    max: 90,
    placeholders: [...COMMON, "amount", "plan", "end_date"],
    example: "automations.dues.example",
  },
  {
    trigger: "not_visiting",
    group: "membership",
    title: "automations.notVisiting.title",
    help: "automations.notVisiting.help",
    min: 3,
    max: 180,
    placeholders: [...COMMON, "days", "plan", "end_date"],
    example: "automations.notVisiting.example",
  },
  {
    trigger: "birthday",
    group: "membership",
    title: "automations.birthday.title",
    help: "automations.birthday.help",
    min: 0,
    max: 0,
    placeholders: COMMON,
    example: "automations.birthday.example",
  },
  {
    trigger: "pt_ending",
    group: "pt",
    title: "automations.ptEnding.title",
    help: "automations.ptEnding.help",
    min: -60,
    max: 60,
    placeholders: [...COMMON, "plan", "trainer", "end_date", "days"],
    example: "automations.ptEnding.example",
  },
  {
    trigger: "pt_dues",
    group: "pt",
    title: "automations.ptDues.title",
    help: "automations.ptDues.help",
    min: 1,
    max: 90,
    placeholders: [...COMMON, "amount", "plan", "trainer", "end_date"],
    example: "automations.ptDues.example",
  },
  {
    trigger: "progress",
    group: "progress",
    title: "automations.progress.title",
    help: "automations.progress.help",
    min: 7,
    max: 180,
    placeholders: [...COMMON, "days"],
    example: "automations.progress.example",
    pushOnly: true,
  },
];

/** "3 days before it ends", "After 14 days away", "On their birthday". */
export function when(trigger: Trigger, days: number): string {
  switch (trigger) {
    case "expiry":
    case "pt_ending":
      if (days === 0) return t("automations.when.onTheDay");
      return days < 0
        ? plural(-days, "automations.when.before.one", "automations.when.before.other")
        : plural(days, "automations.when.after.one", "automations.when.after.other");
    case "lapsed":
      return plural(
        days,
        "automations.when.lapsed.one",
        "automations.when.lapsed.other",
      );
    case "dues":
    case "pt_dues":
      return plural(days, "automations.when.dues.one", "automations.when.dues.other");
    case "not_visiting":
      return plural(
        days,
        "automations.when.notVisiting.one",
        "automations.when.notVisiting.other",
      );
    case "birthday":
      return t("automations.when.birthday");
    case "progress":
      return plural(
        days,
        "automations.when.progress.one",
        "automations.when.progress.other",
      );
  }
}
