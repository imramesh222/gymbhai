import { t, type MessageKey } from "@/i18n";

const STYLES: Record<string, string> = {
  active: "bg-emerald-50 text-emerald-800 ring-emerald-600/20",
  frozen: "bg-sky-50 text-sky-800 ring-sky-600/20",
  upcoming: "bg-violet-50 text-violet-800 ring-violet-600/20",
  expired: "bg-red-50 text-red-800 ring-red-600/20",
  cancelled: "bg-slate-100 text-slate-700 ring-slate-500/20",
  none: "bg-slate-50 text-slate-600 ring-slate-500/15",
  voided: "bg-slate-100 text-slate-600 line-through ring-slate-500/20",
};

const DOTS: Record<string, string> = {
  active: "bg-emerald-500",
  frozen: "bg-sky-500",
  upcoming: "bg-violet-500",
  expired: "bg-red-500",
  cancelled: "bg-slate-400",
  none: "bg-slate-300",
  voided: "bg-slate-400",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${
        STYLES[status] ?? STYLES.none
      }`}
    >
      {/* The dot carries the status at a glance; the word confirms it. */}
      <span
        className={`size-1.5 rounded-full ${DOTS[status] ?? DOTS.none}`}
        aria-hidden
      />
      {t(`status.${status}` as MessageKey)}
    </span>
  );
}
