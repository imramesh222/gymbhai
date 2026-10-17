import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import { t } from "@/i18n";

const WORDS = {
  yesterday: {
    more: "today.moreThanYesterday",
    less: "today.lessThanYesterday",
    same: "today.sameAsYesterday",
  },
  lastMonth: {
    more: "reports.moreThanLastMonth",
    less: "reports.lessThanLastMonth",
    same: "reports.sameAsLastMonth",
  },
} as const;

/**
 * "▲ 4 vs this time yesterday". Green when the change is good — up for
 * visits and money, down for members lost — and red when it isn't; an arrow
 * and the words carry it too, never the colour alone.
 */
export function Delta({
  now,
  before,
  format = (value: number) => value.toLocaleString("en-IN"),
  period = "yesterday",
  goodWhenUp = true,
}: {
  now: number;
  before: number;
  format?: (value: number) => string;
  period?: keyof typeof WORDS;
  goodWhenUp?: boolean;
}) {
  const change = now - before;
  const words = WORDS[period];
  const Icon = change > 0 ? ArrowUpRight : change < 0 ? ArrowDownRight : Minus;
  const good = change === 0 ? null : change > 0 === goodWhenUp;
  const tone =
    good === null ? "text-slate-500" : good ? "text-emerald-700" : "text-red-700";
  return (
    <span className={`inline-flex items-center gap-0.5 ${tone}`}>
      <Icon className="size-3.5" aria-hidden />
      {change === 0
        ? t(words.same)
        : t(change > 0 ? words.more : words.less, { amount: format(Math.abs(change)) })}
    </span>
  );
}
