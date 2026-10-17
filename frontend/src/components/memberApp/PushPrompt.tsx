"use client";

import { Bell } from "lucide-react";

import { t } from "@/i18n";
import { usePush } from "@/lib/push";
import { useStoredFlag } from "@/lib/storedFlag";

/**
 * "Get reminders on this phone" on Home, after the first sign-in (PLAN.md
 * §16.3, 8.3). On an iPhone not opened from the Home Screen, how to add it
 * first. Put away with "Not now"; it stays in Profile.
 */
export function PushPrompt({ slug, color }: { slug: string; color: string }) {
  const { state, error, on } = usePush(slug);
  const [dismissed, dismiss] = useStoredFlag(`gb:push-prompt-dismissed:${slug}`);
  // An iPhone not opened from the Home Screen: InstallPrompt says how, and
  // that reminders come once it's installed.
  if (dismissed || state !== "off") return null;

  return (
    <section
      aria-labelledby="push-prompt"
      className="rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline"
    >
      <div className="flex gap-3">
        <span
          className="flex size-10 shrink-0 items-center justify-center rounded-full text-white"
          style={{ background: color }}
        >
          <Bell className="size-5" aria-hidden />
        </span>
        <div className="min-w-0">
          <h2 id="push-prompt" className="font-semibold text-slate-900">
            {t("app.push.title")}
          </h2>
          <p className="mt-0.5 text-sm text-slate-600">{t("app.push.why")}</p>
          {error && <p className="mt-2 text-sm text-red-700">{t("app.push.failed")}</p>}
        </div>
      </div>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={() => void on()}
          className="flex-1 rounded-xl py-2.5 text-sm font-semibold text-white transition active:translate-y-px"
          style={{ background: color }}
        >
          {t("app.push.turnOn")}
        </button>
        <button
          type="button"
          onClick={() => dismiss(true)}
          className="flex-1 rounded-xl bg-slate-100 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-200"
        >
          {t("app.push.notNow")}
        </button>
      </div>
    </section>
  );
}

/** Profile → "Reminders on this phone": on, off, or why it can't be. */
export function PushSetting({ slug }: { slug: string }) {
  const { state, error, on, off } = usePush(slug);
  if (state === "loading" || state === "unavailable") return null;
  const why: Partial<Record<typeof state, string>> = {
    unsupported: t("app.push.unsupported"),
    install: t("app.push.installFirst"),
    blocked: t("app.push.blocked"),
  };
  return (
    <div className="rounded-2xl bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium text-slate-900">{t("app.push.setting")}</p>
          <p className="text-sm text-slate-500">
            {why[state] ?? (state === "on" ? t("app.push.isOn") : t("app.push.isOff"))}
          </p>
        </div>
        {(state === "on" || state === "off") && (
          <button
            type="button"
            role="switch"
            aria-checked={state === "on"}
            aria-label={t("app.push.setting")}
            onClick={() => void (state === "on" ? off() : on())}
            className={`relative h-7 w-12 shrink-0 rounded-full transition ${
              state === "on" ? "bg-brand-600" : "bg-slate-300"
            }`}
          >
            <span
              className={`absolute top-0.5 size-6 rounded-full bg-white shadow transition-all ${
                state === "on" ? "left-[1.375rem]" : "left-0.5"
              }`}
            />
          </button>
        )}
      </div>
      {error && <p className="mt-2 text-sm text-red-700">{t("app.push.failed")}</p>}
    </div>
  );
}
