"use client";

import { EmptyState } from "@/components/ui/Card";
import { t, isMessageKey } from "@/i18n";
import type { HistoryEntry } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { formatRs } from "@/lib/money";

const MONEY_FIELDS = new Set(["price", "discount", "admission_fee", "amount"]);
const DATE_FIELDS = new Set([
  "start_date",
  "end_date",
  "from",
  "to",
  "date_of_birth",
  "joined_on",
]);

/** Who changed what, when, before and after (PLAN.md §5.6). */
export function History({ entries }: { entries: HistoryEntry[] }) {
  const { display, date } = useGymCalendar();

  function show(field: string, value: unknown): string {
    if (value === null || value === undefined || value === "") return "—";
    if (MONEY_FIELDS.has(field) && typeof value === "number") return formatRs(value);
    if (DATE_FIELDS.has(field) && typeof value === "string") return date(value);
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  function label(key: string): string {
    const k = `history.field.${key}`;
    return isMessageKey(k) ? t(k) : key;
  }

  if (entries.length === 0) return <EmptyState title={t("history.none")} />;
  return (
    <ol className="space-y-3">
      {entries.map((entry) => {
        const action = `history.action.${entry.action}`;
        const edits = Object.entries(entry.changes ?? {}).filter(
          ([, v]) => v && typeof v === "object" && "before" in (v as object),
        ) as [string, { before: unknown; after: unknown }][];
        return (
          <li key={entry.id} className="border-l-2 border-hairline pl-3">
            <p className="text-sm font-medium text-slate-900">
              {isMessageKey(action) ? t(action) : entry.action}
            </p>
            <p className="text-xs text-slate-500">
              {formatDateTime(entry.at, display)}
              {entry.actor_name && ` · ${entry.actor_name}`}
            </p>
            {entry.reason && (
              <p className="mt-0.5 text-sm text-slate-700">
                {t("history.reason", { reason: entry.reason })}
              </p>
            )}
            {edits.length > 0 && (
              <ul className="mt-1 space-y-0.5 text-xs text-slate-600">
                {edits.map(([field, change]) => (
                  <li key={field}>
                    {label(field)}:{" "}
                    <span className="line-through">{show(field, change.before)}</span> →{" "}
                    <span className="font-medium text-slate-900">
                      {show(field, change.after)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </li>
        );
      })}
    </ol>
  );
}
