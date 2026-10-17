"use client";

import { Plus, Share, Smartphone } from "lucide-react";
import { useState } from "react";

import { Dialog } from "@/components/ui/Dialog";
import { t } from "@/i18n";
import { useInstall } from "@/lib/install";
import { useStoredFlag } from "@/lib/storedFlag";

/** The steps on an iPhone, which has no install button of its own. */
export function IosSteps() {
  return (
    <ol className="list-decimal space-y-2 pl-5 text-sm text-slate-700">
      <li>
        {t("app.install.ios1")}{" "}
        <Share
          className="inline size-4 align-text-bottom"
          aria-label={t("app.push.share")}
        />
      </li>
      <li>
        {t("app.install.ios2")}{" "}
        <Plus className="inline size-4 align-text-bottom" aria-hidden />
      </li>
      <li>{t("app.install.ios3")}</li>
    </ol>
  );
}

/**
 * "Add GymBhai to your Home Screen" on Home (PLAN.md §16.3, 8.5): Android's
 * own install prompt, or the steps on an iPhone. Gone once installed, or put
 * away with "Not now".
 */
export function InstallPrompt({ slug, color }: { slug: string; color: string }) {
  const { way, install } = useInstall();
  const [dismissed, dismiss] = useStoredFlag(`gb:install-dismissed:${slug}`);
  const [steps, setSteps] = useState(false);
  if (!way || dismissed) return null;

  return (
    <section
      aria-labelledby="install-prompt"
      className="rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline"
    >
      <div className="flex gap-3">
        <span
          className="flex size-10 shrink-0 items-center justify-center rounded-full text-white"
          style={{ background: color }}
        >
          <Smartphone className="size-5" aria-hidden />
        </span>
        <div className="min-w-0">
          <h2 id="install-prompt" className="font-semibold text-slate-900">
            {t("app.install.title")}
          </h2>
          <p className="mt-0.5 text-sm text-slate-600">
            {way === "ios" ? t("app.install.whyIos") : t("app.install.why")}
          </p>
        </div>
      </div>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={() => (way === "ios" ? setSteps(true) : void install())}
          className="flex-1 rounded-xl py-2.5 text-sm font-semibold text-white transition active:translate-y-px"
          style={{ background: color }}
        >
          {way === "ios" ? t("app.install.how") : t("app.install.install")}
        </button>
        <button
          type="button"
          onClick={() => dismiss(true)}
          className="flex-1 rounded-xl bg-slate-100 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-200"
        >
          {t("app.push.notNow")}
        </button>
      </div>
      {steps && (
        <Dialog open onClose={() => setSteps(false)} title={t("app.install.title")}>
          <IosSteps />
        </Dialog>
      )}
    </section>
  );
}
