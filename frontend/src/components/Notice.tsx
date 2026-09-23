const TONES = {
  error: "bg-red-50 text-red-900 ring-red-200/70",
  warning: "bg-amber-50 text-amber-950 ring-amber-200/70",
  info: "bg-brand-50 text-brand-900 ring-brand-200/70",
  success: "bg-emerald-50 text-emerald-950 ring-emerald-200/70",
} as const;

const MARKS = {
  error: "bg-red-600",
  warning: "bg-amber-500",
  info: "bg-brand-600",
  success: "bg-emerald-600",
} as const;

export function Notice({
  tone = "info",
  children,
}: {
  tone?: keyof typeof TONES;
  children: React.ReactNode;
}) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`flex gap-3 rounded-xl px-3.5 py-3 text-sm ring-1 ring-inset ${TONES[tone]}`}
    >
      {/* A colour bar rather than an icon: it reads at a glance and needs no
          translation. */}
      <span className={`mt-0.5 w-1 shrink-0 rounded-full ${MARKS[tone]}`} aria-hidden />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
