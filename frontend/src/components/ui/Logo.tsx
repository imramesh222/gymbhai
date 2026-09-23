import { t } from "@/i18n";

/** The mark: a dumbbell in a brand tile. Used wherever the product signs its name. */
export function LogoMark({ className = "size-9" }: { className?: string }) {
  return (
    <span
      className={`${className} flex shrink-0 items-center justify-center rounded-xl bg-linear-to-br from-brand-500 to-brand-700 text-white shadow-brand`}
      aria-hidden
    >
      <svg viewBox="0 0 24 24" fill="none" className="size-[62%]">
        <path
          d="M4 9v6M7 7v10M17 7v10M20 9v6M7 12h10"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}

export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`flex items-center gap-2.5 ${className}`}>
      <LogoMark />
      <span className="text-lg font-bold tracking-tight text-slate-900">
        {t("app.name")}
      </span>
    </span>
  );
}
