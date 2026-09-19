"use client";

import { Money } from "@/components/ui/Money";
import { t, type MessageKey } from "@/i18n";
import type { ScanResult } from "@/lib/api";
import { formatDate, type DateDisplay } from "@/lib/dates";

/**
 * What the door shows (PLAN.md §4.3):
 *   green  — "Welcome, Sita — 23 days left", with her photo
 *   orange — allowed, but renew soon / owes money / in grace days
 *   red    — "Membership expired on 3 Kartik — please see the desk"
 */
export function tone(result: ScanResult): "green" | "orange" | "red" {
  if (!result.let_in) return "red";
  if (result.result === "warned" || result.result === "override") return "orange";
  if (result.days_left <= 3 || result.dues > 0) return "orange";
  return "green";
}

const STYLES = {
  green: "bg-emerald-600",
  orange: "bg-amber-500",
  red: "bg-red-600",
};

export function ScanCard({
  result,
  display,
}: {
  result: ScanResult;
  display: DateDisplay;
}) {
  const colour = tone(result);
  const first = result.member_name?.split(" ")[0] ?? "";
  let headline: string;
  if (result.result === "unknown") headline = t("door.unknown");
  else if (result.result === "duplicate")
    headline = t("door.duplicate", { name: first });
  else if (result.let_in)
    headline = t("door.welcome", { name: first, count: result.days_left });
  else
    headline = t(`door.denied.${result.reason ?? "expired"}` as MessageKey, {
      date: formatDate(result.valid_until, display),
    });

  return (
    <div
      className={`rounded-3xl p-6 text-center text-white ${STYLES[colour]}`}
      role="status"
    >
      {result.photo_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={result.photo_url}
          alt=""
          className="mx-auto mb-4 size-40 rounded-full border-4 border-white object-cover"
        />
      )}
      <p className="text-3xl font-bold">{headline}</p>
      {result.member_code && <p className="mt-1 opacity-90">{result.member_code}</p>}
      {result.let_in && result.days_left <= 3 && result.result !== "duplicate" && (
        <p className="mt-3 text-xl font-semibold">{t("door.renewSoon")}</p>
      )}
      {result.dues > 0 && (
        <p className="mt-2 text-lg">
          {t("door.owes")} <Money paisa={result.dues} />
        </p>
      )}
      {result.reason === "expired_grace" && (
        <p className="mt-2 text-lg">{t("door.grace")}</p>
      )}
    </div>
  );
}
