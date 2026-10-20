"use client";

import { Smartphone } from "lucide-react";

import { t } from "@/i18n";
import type { PublicGym } from "@shared/types";

/**
 * The gym's own app in the stores (PLAN.md §20.3), on Home instead of
 * "add GymBhai to your Home Screen": the store links for this phone.
 */
export function OwnAppPrompt({
  app,
  color,
}: {
  app: NonNullable<PublicGym["app"]>;
  color: string;
}) {
  const iphone =
    typeof navigator !== "undefined" && /iPhone|iPad|iPod/.test(navigator.userAgent);
  const links = [
    ...(app.play_url && !iphone
      ? [{ href: app.play_url, label: t("ownApp.playStore") }]
      : []),
    ...(app.app_store_url
      ? [{ href: app.app_store_url, label: t("ownApp.appStore") }]
      : []),
    ...(app.play_url && iphone
      ? [{ href: app.play_url, label: t("ownApp.playStore") }]
      : []),
  ];
  if (links.length === 0) return null;
  return (
    <section
      aria-labelledby="own-app"
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
          <h2 id="own-app" className="font-semibold text-slate-900">
            {t("ownApp.get", { name: app.name })}
          </h2>
          <p className="mt-0.5 text-sm text-slate-600">{t("ownApp.getHelp")}</p>
        </div>
      </div>
      <div className="mt-3 flex gap-2">
        {links.map((link) => (
          <a
            key={link.href}
            href={link.href}
            target="_blank"
            rel="noreferrer"
            className="flex-1 rounded-xl py-2.5 text-center text-sm font-semibold text-white"
            style={{ background: color }}
          >
            {link.label}
          </a>
        ))}
      </div>
    </section>
  );
}
