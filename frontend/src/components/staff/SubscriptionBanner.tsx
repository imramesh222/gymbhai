"use client";

import Link from "next/link";

import { plural, t } from "@/i18n";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";

/** The trial and lapse banners (PLAN.md §5.7). Red in grace; read-only after. */
export function SubscriptionBanner() {
  const { me, can } = useAuth();
  const { display } = useGymCalendar();
  const sub = me?.subscription;
  if (!sub) return null;
  const pay = can("setup.gym") && (
    <Link href="/staff/subscription" className="ml-2 font-semibold underline">
      {t("subscription.payNow")}
    </Link>
  );
  let text: string | null = null;
  let tone = "bg-brand-50 text-brand-900";
  if (sub.phase === "read_only") {
    text = t("subscription.banner.readOnly");
    tone = "bg-red-600 text-white";
  } else if (sub.phase === "grace") {
    text = t("subscription.banner.grace", {
      date: formatDate(sub.grace_ends_on, display),
    });
    tone = "bg-red-100 text-red-900";
  } else if (sub.phase === "ending") {
    text =
      sub.status === "trial"
        ? plural(sub.days_left, "staff.trialDaysLeft.one", "staff.trialDaysLeft.other")
        : t("subscription.banner.ending", { date: formatDate(sub.ends_on, display) });
    tone = "bg-amber-100 text-amber-900";
  } else if (sub.status === "trial") {
    text = plural(
      sub.days_left,
      "staff.trialDaysLeft.one",
      "staff.trialDaysLeft.other",
    );
  }
  if (sub.over_limit) {
    text = `${text ? `${text} ` : ""}${t("subscription.banner.overLimit")}`;
  }
  if (!text) return null;
  return (
    <div
      className={`border-b border-black/5 px-4 py-2 text-center text-sm font-medium print:hidden ${tone}`}
      role="status"
    >
      {text}
      {pay}
    </div>
  );
}
