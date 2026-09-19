"use client";

import { useId } from "react";

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
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-slate-800">
        {label}
        {optional && optionalLabel && (
          <span className="ml-1 font-normal text-slate-500">({optionalLabel})</span>
        )}
      </label>
      <div className="mt-1 flex rounded-lg border border-slate-300 bg-white focus-within:border-brand-600 focus-within:ring-2 focus-within:ring-brand-100">
        {prefix && (
          <span className="flex items-center border-r border-slate-200 px-3 text-sm text-slate-500">
            {prefix}
          </span>
        )}
        <input
          id={id}
          name={name}
          type={type}
          value={value}
          required={required}
          autoComplete={autoComplete}
          inputMode={inputMode}
          aria-describedby={helpId}
          onChange={(e) => onChange(e.target.value)}
          className="w-full min-w-0 rounded-lg bg-transparent px-3 py-2.5 text-base text-slate-900 outline-none"
        />
      </div>
      {help && (
        <p id={helpId} className="mt-1 text-sm text-slate-500">
          {help}
        </p>
      )}
    </div>
  );
}
