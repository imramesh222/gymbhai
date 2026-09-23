"use client";

import { useId, useState } from "react";

import { t } from "@/i18n";
import {
  BS_MONTHS,
  daysInBsMonth,
  formatAd,
  formatBs,
  fromBs,
  todayInNepal,
  toBs,
  type BsDate,
  type DateDisplay,
} from "@/lib/dates";

// Years a membership could plausibly start or end in.
const BS_YEARS = Array.from({ length: 16 }, (_, i) => 2075 + i);
import { parseRs, toInput } from "@/lib/money";

const box =
  "mt-1.5 w-full rounded-xl bg-white px-3 py-2.5 text-base text-slate-900 ring-1 ring-hairline outline-none transition focus:ring-2 focus:ring-brand-500";

function Label({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="block text-sm font-medium text-slate-700">
      {children}
    </label>
  );
}

/** Rupees on screen, paisa in state. */
export function MoneyInput({
  label,
  value,
  onChange,
  required,
  help,
}: {
  label: string;
  value: number | null;
  onChange: (paisa: number | null) => void;
  required?: boolean;
  help?: string;
}) {
  const id = useId();
  const [text, setText] = useState(toInput(value));
  const [lastValue, setLastValue] = useState(value);
  // Follow outside changes (a plan picked, a price filled in).
  if (value !== lastValue) {
    setLastValue(value);
    if (parseRs(text) !== value) setText(toInput(value));
  }
  const invalid = text !== "" && parseRs(text) === null;
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <span className="pointer-events-none absolute top-1/2 left-3 mt-0.5 -translate-y-1/2 text-sm text-slate-500">
          Rs
        </span>
        <input
          id={id}
          inputMode="decimal"
          value={text}
          required={required}
          aria-invalid={invalid}
          onChange={(e) => {
            setText(e.target.value);
            const paisa = parseRs(e.target.value);
            setLastValue(paisa);
            onChange(paisa);
          }}
          className={`${box} pl-9 ${invalid ? "ring-2 ring-red-400" : ""}`}
        />
      </div>
      {help && <p className="mt-1 text-xs text-slate-500">{help}</p>}
    </div>
  );
}

/**
 * A date, stored in AD. Gyms that think in BS (PLAN.md §5.1) can enter it in
 * BS too: year, month and day of the BS calendar, converted as they choose.
 */
export function DateInput({
  label,
  value,
  onChange,
  display,
  required,
}: {
  label: string;
  value: string;
  onChange: (iso: string) => void;
  display: DateDisplay;
  required?: boolean;
}) {
  const id = useId();
  const [inBs, setInBs] = useState(display === "bs");
  let bs: BsDate | null = null;
  try {
    bs = value ? toBs(value) : null;
  } catch {
    bs = null;
  }
  const canBs = display !== "ad";

  function setBs(patch: Partial<BsDate>) {
    const base = bs ?? toBs(todayInNepal());
    const next = { ...base, ...patch };
    next.day = Math.min(next.day, daysInBsMonth(next.year, next.month));
    onChange(fromBs(next));
  }

  const small =
    "rounded-xl bg-white px-2 py-2.5 text-base ring-1 ring-hairline outline-none transition focus:ring-2 focus:ring-brand-500";
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <Label htmlFor={id}>{label}</Label>
        {canBs && (
          <button
            type="button"
            onClick={() => setInBs(!inBs)}
            className="text-xs font-medium text-brand-700 hover:underline"
          >
            {inBs ? t("date.enterAd") : t("date.enterBs")}
          </button>
        )}
      </div>
      {inBs && canBs ? (
        <div
          className="mt-1 grid grid-cols-[1fr_2fr_1fr] gap-2"
          role="group"
          aria-label={label}
        >
          <select
            id={id}
            aria-label={t("date.bsYear")}
            value={bs?.year ?? ""}
            onChange={(e) => setBs({ year: Number(e.target.value) })}
            className={small}
          >
            {!bs && <option value="">—</option>}
            {BS_YEARS.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
          <select
            aria-label={t("date.bsMonth")}
            value={bs?.month ?? ""}
            onChange={(e) => setBs({ month: Number(e.target.value) })}
            className={small}
          >
            {!bs && <option value="">—</option>}
            {BS_MONTHS.map((name, i) => (
              <option key={name} value={i + 1}>
                {name}
              </option>
            ))}
          </select>
          <select
            aria-label={t("date.bsDay")}
            value={bs?.day ?? ""}
            onChange={(e) => setBs({ day: Number(e.target.value) })}
            className={small}
          >
            {!bs && <option value="">—</option>}
            {Array.from(
              { length: bs ? daysInBsMonth(bs.year, bs.month) : 32 },
              (_, i) => i + 1,
            ).map((day) => (
              <option key={day} value={day}>
                {day}
              </option>
            ))}
          </select>
        </div>
      ) : (
        <input
          id={id}
          type="date"
          value={value}
          required={required}
          onChange={(e) => onChange(e.target.value)}
          className={box}
        />
      )}
      {value && canBs && (
        <p className="mt-1 text-xs text-slate-600">
          {inBs ? formatAd(value) : bs ? t("date.bsIs", { date: formatBs(value) }) : ""}
        </p>
      )}
    </div>
  );
}

export function Select<T extends string>({
  label,
  value,
  onChange,
  options,
  required,
  compact,
}: {
  label: string;
  value: T | "";
  onChange: (value: T) => void;
  options: { value: T; label: string }[];
  required?: boolean;
  /** In a table row, where the column heading already says what it is. */
  compact?: boolean;
}) {
  const id = useId();
  return (
    <div>
      {compact ? (
        <label htmlFor={id} className="sr-only">
          {label}
        </label>
      ) : (
        <Label htmlFor={id}>{label}</Label>
      )}
      <select
        id={id}
        value={value}
        required={required}
        onChange={(e) => onChange(e.target.value as T)}
        className={
          compact
            ? "w-full rounded-lg bg-white px-2.5 py-1.5 text-sm text-slate-700 ring-1 ring-hairline outline-none transition hover:bg-slate-50 focus:ring-2 focus:ring-brand-500"
            : box
        }
      >
        <option value="" disabled>
          {t("common.choose")}
        </option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function TextArea({
  label,
  value,
  onChange,
  required,
  rows = 2,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  rows?: number;
}) {
  const id = useId();
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      <textarea
        id={id}
        value={value}
        rows={rows}
        required={required}
        onChange={(e) => onChange(e.target.value)}
        className={box}
      />
    </div>
  );
}

export function Checkbox({
  label,
  checked,
  onChange,
  disabled,
  hint,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  hint?: string;
}) {
  return (
    <label
      className={`flex items-start gap-2 py-1 text-sm ${disabled ? "opacity-50" : "cursor-pointer"}`}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 size-4 accent-brand-600"
      />
      <span>
        <span className="text-slate-900">{label}</span>
        {hint && <span className="block text-xs text-slate-500">{hint}</span>}
      </span>
    </label>
  );
}
