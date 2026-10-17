"use client";

import { Plus, Trash2 } from "lucide-react";

import { t } from "@/i18n";
import { dayName, type AccessWindow } from "@/lib/accessHours";

const input =
  "w-full rounded-xl bg-white px-3 py-2 text-base ring-1 ring-hairline outline-none focus:ring-2 focus:ring-brand-500";

/** An off-peak plan's hours: days and a time range, one or more (9.4). */
export function AccessHoursEditor({
  value,
  onChange,
}: {
  value: AccessWindow[];
  onChange: (hours: AccessWindow[]) => void;
}) {
  const set = (i: number, next: AccessWindow) =>
    onChange(value.map((w, j) => (j === i ? next : w)));
  return (
    <div className="space-y-3">
      {value.map((w, i) => (
        <fieldset key={i} className="space-y-2 rounded-xl p-3 ring-1 ring-hairline">
          <legend className="sr-only">{t("plans.hoursWindow", { n: i + 1 })}</legend>
          <div className="flex flex-wrap gap-1.5">
            {[0, 1, 2, 3, 4, 5, 6].map((day) => {
              const on = w.days.includes(day);
              return (
                <button
                  key={day}
                  type="button"
                  aria-pressed={on}
                  onClick={() =>
                    set(i, {
                      ...w,
                      days: on ? w.days.filter((d) => d !== day) : [...w.days, day],
                    })
                  }
                  className={`rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${
                    on
                      ? "bg-brand-600 text-white ring-brand-600"
                      : "bg-white text-slate-600 ring-hairline"
                  }`}
                >
                  {dayName(day)}
                </button>
              );
            })}
          </div>
          <div className="flex items-end gap-2">
            <label className="flex-1 text-sm font-medium text-slate-700">
              {t("plans.hoursFrom")}
              <input
                type="time"
                value={w.from}
                onChange={(e) => set(i, { ...w, from: e.target.value })}
                className={input}
                required
              />
            </label>
            <label className="flex-1 text-sm font-medium text-slate-700">
              {t("plans.hoursTo")}
              <input
                type="time"
                value={w.to}
                onChange={(e) => set(i, { ...w, to: e.target.value })}
                className={input}
                required
              />
            </label>
            <button
              type="button"
              onClick={() => onChange(value.filter((_, j) => j !== i))}
              className="mb-1 rounded-lg p-2 text-slate-500 hover:bg-slate-100"
              aria-label={t("plans.hoursRemove")}
            >
              <Trash2 className="size-4" aria-hidden />
            </button>
          </div>
        </fieldset>
      ))}
      <button
        type="button"
        onClick={() =>
          onChange([...value, { days: [0, 1, 2, 3, 4], from: "06:00", to: "10:00" }])
        }
        className="inline-flex items-center gap-1 text-sm font-semibold text-brand-700"
      >
        <Plus className="size-4" aria-hidden />
        {t("plans.hoursAdd")}
      </button>
    </div>
  );
}
