"use client";

import { useLocale } from "@/lib/locale";

/**
 * English | नेपाली, before anyone has signed in (PLAN.md §16.6). Each name
 * in its own language, so whoever needs it can find it.
 */
export function LanguageSwitch({
  className = "",
  dark = false,
}: {
  className?: string;
  /** On a photo or a dark band, as on the home page. */
  dark?: boolean;
}) {
  const { locale, change } = useLocale();
  const option = (value: "en" | "ne", label: string) => (
    <button
      type="button"
      lang={value}
      aria-pressed={locale === value}
      onClick={() => change(value)}
      className={`rounded-full px-3 py-1 text-sm font-medium transition ${
        locale === value
          ? dark
            ? "bg-white text-slate-900"
            : "bg-slate-900 text-white"
          : dark
            ? "text-white/75 hover:bg-white/10 hover:text-white"
            : "text-slate-600 hover:bg-slate-100"
      }`}
    >
      {label}
    </button>
  );
  return (
    <div
      className={`inline-flex gap-1 rounded-full p-1 ring-1 ${
        dark ? "bg-white/10 ring-white/15 backdrop-blur" : "bg-white ring-hairline"
      } ${className}`}
    >
      {option("en", "English")}
      {option("ne", "नेपाली")}
    </div>
  );
}
