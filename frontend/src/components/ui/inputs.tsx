"use client";

import { useId, useState } from "react";

import { t } from "@/i18n";
import { formatBs, type DateDisplay } from "@/lib/dates";
import { parseRs, toInput } from "@/lib/money";

const box =
  "mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-base text-slate-900 outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100";

function Label({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="block text-sm font-medium text-slate-800">
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
          className={`${box} pl-9 ${invalid ? "border-red-400" : ""}`}
        />
      </div>
      {help && <p className="mt-1 text-xs text-slate-500">{help}</p>}
    </div>
  );
}

/** An AD date picker that also shows the BS date, for gyms that think in BS. */
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
  let bs = "";
  try {
    bs = value && display !== "ad" ? formatBs(value) : "";
  } catch {
    bs = "";
  }
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      <input
        id={id}
        type="date"
        value={value}
        required={required}
        onChange={(e) => onChange(e.target.value)}
        className={box}
      />
      {bs && (
        <p className="mt-1 text-xs text-slate-600">{t("date.bsIs", { date: bs })}</p>
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
}: {
  label: string;
  value: T | "";
  onChange: (value: T) => void;
  options: { value: T; label: string }[];
  required?: boolean;
}) {
  const id = useId();
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      <select
        id={id}
        value={value}
        required={required}
        onChange={(e) => onChange(e.target.value as T)}
        className={box}
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
