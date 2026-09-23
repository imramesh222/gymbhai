import Link from "next/link";

/** The one panel everything sits in: a white surface lifted off the canvas. */
export function Card({
  title,
  actions,
  children,
  className = "",
}: {
  title?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline sm:p-5 ${className}`}
    >
      {(title || actions) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && (
            <h2 className="text-[0.9375rem] font-semibold text-slate-900">{title}</h2>
          )}
          {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

/** A card whose children run edge to edge: lists, tables, rows. */
export function ListCard({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`overflow-hidden rounded-2xl bg-surface shadow-card ring-1 ring-hairline ${className}`}
    >
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-[1.75rem]">
          {title}
        </h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2 print:hidden">{actions}</div>}
    </div>
  );
}

export function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-sm">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-medium text-slate-900">{children}</dd>
    </div>
  );
}

const TONES = {
  plain: "text-slate-900",
  brand: "text-brand-700",
  warning: "text-amber-700",
  danger: "text-red-600",
  good: "text-emerald-700",
} as const;

/** One number, big. The label is above the value: the eye lands on the number. */
export function Stat({
  value,
  label,
  href,
  tone = "plain",
  hint,
}: {
  value: React.ReactNode;
  label: string;
  href?: string;
  tone?: keyof typeof TONES;
  hint?: React.ReactNode;
}) {
  const body = (
    <div
      className={`h-full rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline transition ${
        href ? "hover:-translate-y-0.5 hover:shadow-raised hover:ring-brand-200" : ""
      }`}
    >
      <p className="text-[0.6875rem] font-semibold tracking-wider text-slate-500 uppercase">
        {label}
      </p>
      <p className={`mt-1.5 text-3xl font-bold tracking-tight ${TONES[tone]}`}>
        {value}
      </p>
      {hint && <p className="mt-0.5 text-xs text-slate-500">{hint}</p>}
    </div>
  );
  return href ? (
    <Link href={href} className="block">
      {body}
    </Link>
  ) : (
    body
  );
}

/** What a list says when it has nothing in it. */
export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="px-6 py-8 text-center">
      <p className="text-sm font-medium text-slate-500">{title}</p>
      {hint && <p className="mx-auto mt-1 max-w-sm text-sm text-slate-500">{hint}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}
