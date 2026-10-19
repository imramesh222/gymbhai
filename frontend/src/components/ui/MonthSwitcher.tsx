"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/Button";
import { t } from "@/i18n";
import { monthName, shiftMonth } from "@/lib/months";

/** Previous · Kartik 2083 · Next: a month of the gym's own calendar. */
export function MonthSwitcher({
  month,
  calendar,
  onChange,
}: {
  month: string;
  calendar: "ad" | "bs";
  onChange: (month: string) => void;
}) {
  return (
    <div className="flex items-center justify-between rounded-xl bg-white p-1.5 shadow-card ring-1 ring-hairline print:hidden">
      <Button variant="ghost" onClick={() => onChange(shiftMonth(month, -1))}>
        <ChevronLeft className="size-4" aria-hidden />
        {t("common.previous")}
      </Button>
      <p className="font-semibold">{monthName(month, calendar, true)}</p>
      <Button variant="ghost" onClick={() => onChange(shiftMonth(month, 1))}>
        {t("common.next")}
        <ChevronRight className="size-4" aria-hidden />
      </Button>
    </div>
  );
}
