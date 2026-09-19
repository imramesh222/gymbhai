import { t, type MessageKey } from "@/i18n";

const STYLES: Record<string, string> = {
  active: "bg-emerald-100 text-emerald-800",
  frozen: "bg-sky-100 text-sky-800",
  upcoming: "bg-violet-100 text-violet-800",
  expired: "bg-red-100 text-red-800",
  cancelled: "bg-slate-200 text-slate-700",
  none: "bg-slate-100 text-slate-600",
  voided: "bg-slate-200 text-slate-600 line-through",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
        STYLES[status] ?? STYLES.none
      }`}
    >
      {t(`status.${status}` as MessageKey)}
    </span>
  );
}
