"use client";

import { Bell } from "lucide-react";

import { Button } from "@/components/Button";
import { Card } from "@/components/ui/Card";
import { Checkbox } from "@/components/ui/inputs";
import { t, type MessageKey } from "@/i18n";
import type { NotificationKind } from "@/lib/api";
import { useStaffPush } from "@/lib/staffPush";
import { useStoredFlag } from "@/lib/storedFlag";

/**
 * My account → Notifications (PLAN.md §18.6): this device on or off, or why it
 * can't be, and which kinds, for every device of theirs. Not shown to staff
 * whose permissions show none of the three.
 */
export function NotificationsCard() {
  const { state, kinds, muted, error, on, off, choose } = useStaffPush();
  if (state === "loading" || kinds.length === 0) return null;
  const why: Partial<Record<typeof state, MessageKey>> = {
    unsupported: "app.push.unsupported",
    install: "notify.install",
    blocked: "notify.blocked",
    unavailable: "notify.unavailable",
  };
  const reason = why[state];

  function toggle(kind: NotificationKind, wanted: boolean) {
    void choose(wanted ? muted.filter((k) => k !== kind) : [...muted, kind]);
  }

  return (
    <Card title={t("notify.title")}>
      <p className="text-sm text-slate-600">{t("notify.why")}</p>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm font-medium text-slate-900" role="status">
          {reason ? t(reason) : state === "on" ? t("notify.isOn") : t("notify.isOff")}
        </p>
        {state === "off" && (
          <Button size="sm" onClick={() => void on()}>
            {t("app.push.turnOn")}
          </Button>
        )}
        {state === "on" && (
          <Button size="sm" variant="secondary" onClick={() => void off()}>
            {t("notify.turnOff")}
          </Button>
        )}
      </div>
      {error && <p className="mt-2 text-sm text-red-700">{t("app.push.failed")}</p>}
      <fieldset className="mt-4 space-y-2">
        <legend className="mb-1 text-sm font-semibold text-slate-800">
          {t("notify.kinds")}
        </legend>
        {kinds.map((kind) => (
          <Checkbox
            key={kind}
            label={t(`notify.kind.${kind}` as MessageKey)}
            checked={!muted.includes(kind)}
            onChange={(wanted) => toggle(kind, wanted)}
          />
        ))}
      </fieldset>
      <p className="mt-3 text-xs text-slate-500">{t("notify.signedOut")}</p>
    </Card>
  );
}

/**
 * On Today, once: "Get notified on this device", for staff who'd get any,
 * until it's on or put away with "Not now". It stays in My account.
 */
export function NotificationsPrompt() {
  const { state, kinds, error, on } = useStaffPush();
  const [dismissed, dismiss] = useStoredFlag("gb:staff-push-prompt-dismissed");
  if (dismissed || state !== "off" || kinds.length === 0) return null;
  return (
    <section
      aria-labelledby="notify-prompt"
      className="flex flex-wrap items-center gap-3 rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline"
    >
      <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-brand-600 text-white">
        <Bell className="size-5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <h2 id="notify-prompt" className="font-semibold text-slate-900">
          {t("notify.promptTitle")}
        </h2>
        <p className="text-sm text-slate-600">{t("notify.why")}</p>
        {error && <p className="mt-1 text-sm text-red-700">{t("app.push.failed")}</p>}
      </div>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => void on()}>
          {t("app.push.turnOn")}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => dismiss(true)}>
          {t("app.push.notNow")}
        </Button>
      </div>
    </section>
  );
}
