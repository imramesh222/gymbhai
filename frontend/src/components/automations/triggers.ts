import type { MessageKey } from "@/i18n";
import { t } from "@/i18n";
import type { Trigger } from "@/lib/api";

/** What each automation's `days` means, and what it may say (PLAN.md §16.3, 8.2). */
export interface TriggerInfo {
  trigger: Trigger;
  title: MessageKey;
  help: MessageKey;
  min: number;
  max: number;
  /** The placeholders a message for this trigger can fill in. */
  placeholders: string[];
  /** A starting wording for a new one. */
  example: MessageKey;
}

const COMMON = ["name", "gym", "link", "code"];

export const TRIGGERS: TriggerInfo[] = [
  {
    trigger: "expiry",
    title: "automations.expiry.title",
    help: "automations.expiry.help",
    min: -60,
    max: 60,
    placeholders: [...COMMON, "plan", "end_date", "days"],
    example: "automations.expiry.example",
  },
  {
    trigger: "lapsed",
    title: "automations.lapsed.title",
    help: "automations.lapsed.help",
    min: 1,
    max: 365,
    placeholders: [...COMMON, "plan", "end_date", "days"],
    example: "automations.lapsed.example",
  },
  {
    trigger: "dues",
    title: "automations.dues.title",
    help: "automations.dues.help",
    min: 1,
    max: 90,
    placeholders: [...COMMON, "amount", "plan", "end_date"],
    example: "automations.dues.example",
  },
  {
    trigger: "not_visiting",
    title: "automations.notVisiting.title",
    help: "automations.notVisiting.help",
    min: 3,
    max: 180,
    placeholders: [...COMMON, "days", "plan", "end_date"],
    example: "automations.notVisiting.example",
  },
  {
    trigger: "birthday",
    title: "automations.birthday.title",
    help: "automations.birthday.help",
    min: 0,
    max: 0,
    placeholders: COMMON,
    example: "automations.birthday.example",
  },
];

/** "3 days before it ends", "After 14 days away", "On their birthday". */
export function when(trigger: Trigger, days: number): string {
  switch (trigger) {
    case "expiry":
      if (days === 0) return t("automations.when.onTheDay");
      return days < 0
        ? t("automations.when.before", { count: -days })
        : t("automations.when.after", { count: days });
    case "lapsed":
      return t("automations.when.lapsed", { count: days });
    case "dues":
      return t("automations.when.dues", { count: days });
    case "not_visiting":
      return t("automations.when.notVisiting", { count: days });
    case "birthday":
      return t("automations.when.birthday");
  }
}
