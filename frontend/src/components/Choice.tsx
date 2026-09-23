"use client";

import { useId } from "react";

export interface ChoiceOption<T extends string> {
  value: T;
  label: string;
  hint?: string;
}

interface ChoiceProps<T extends string> {
  legend: string;
  name: string;
  options: ChoiceOption<T>[];
  value: T | null;
  onChange: (value: T) => void;
  required?: boolean;
  columns?: 2 | 3;
}

/** Radio buttons drawn as cards. Nothing is pre-selected unless `value` is set. */
export function Choice<T extends string>({
  legend,
  name,
  options,
  value,
  onChange,
  required,
  columns = 2,
}: ChoiceProps<T>) {
  const id = useId();
  return (
    <fieldset>
      <legend className="text-sm font-medium text-slate-700">{legend}</legend>
      <div
        className={`mt-2 grid gap-2.5 ${columns === 3 ? "grid-cols-3" : "sm:grid-cols-2"}`}
      >
        {options.map((option) => {
          const optionId = `${id}-${option.value}`;
          const checked = value === option.value;
          return (
            <label
              key={option.value}
              htmlFor={optionId}
              className={`cursor-pointer rounded-xl px-3.5 py-3 ring-1 transition ${
                checked
                  ? "bg-brand-50 text-brand-900 ring-2 ring-brand-600"
                  : "bg-white ring-hairline hover:bg-slate-50 hover:ring-slate-300"
              }`}
            >
              <input
                id={optionId}
                type="radio"
                name={name}
                value={option.value}
                checked={checked}
                required={required}
                onChange={() => onChange(option.value)}
                className="sr-only"
              />
              <span className="block text-sm font-semibold">{option.label}</span>
              {option.hint && (
                <span className="mt-0.5 block text-xs opacity-70">{option.hint}</span>
              )}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
