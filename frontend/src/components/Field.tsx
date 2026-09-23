"use client";

import { useId, useState } from "react";

import { t } from "@/i18n";

interface FieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  required?: boolean;
  optional?: boolean;
  optionalLabel?: string;
  help?: string;
  autoComplete?: string;
  inputMode?: React.HTMLAttributes<HTMLInputElement>["inputMode"];
  prefix?: string;
  name?: string;
}

/** An eye, struck through once the password is on screen. */
function EyeIcon({ revealed }: { revealed: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="size-5"
      aria-hidden
    >
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="3" />
      {revealed && <path d="m4 20 16-16" />}
    </svg>
  );
}

export function Field({
  label,
  value,
  onChange,
  type = "text",
  required,
  optional,
  optionalLabel,
  help,
  autoComplete,
  inputMode,
  prefix,
  name,
}: FieldProps) {
  const id = useId();
  const helpId = help ? `${id}-help` : undefined;
  // Typing a password on a phone, at a noisy front desk, with the gym's own
  // members watching: let them check what they typed.
  const [revealed, setRevealed] = useState(false);
  const isPassword = type === "password";
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">
        {label}
        {optional && optionalLabel && (
          <span className="ml-1 font-normal text-slate-400">({optionalLabel})</span>
        )}
      </label>
      <div className="mt-1.5 flex rounded-xl bg-white ring-1 ring-hairline transition focus-within:ring-2 focus-within:ring-brand-500">
        {prefix && (
          <span className="flex items-center rounded-l-xl bg-slate-50 px-3 text-sm text-slate-500">
            {prefix}
          </span>
        )}
        <input
          id={id}
          name={name}
          type={isPassword && revealed ? "text" : type}
          value={value}
          required={required}
          autoComplete={autoComplete}
          inputMode={inputMode}
          aria-describedby={helpId}
          onChange={(e) => onChange(e.target.value)}
          className="w-full min-w-0 rounded-xl bg-transparent px-3 py-2.5 text-base text-slate-900 outline-none placeholder:text-slate-400"
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setRevealed(!revealed)}
            aria-label={t(revealed ? "common.hidePassword" : "common.showPassword")}
            aria-pressed={revealed}
            className="mr-1 rounded-lg px-2.5 text-slate-400 transition hover:text-slate-700"
          >
            <EyeIcon revealed={revealed} />
          </button>
        )}
      </div>
      {help && (
        <p id={helpId} className="mt-1.5 text-sm text-slate-500">
          {help}
        </p>
      )}
    </div>
  );
}
