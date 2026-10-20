/**
 * The pieces of Renew in the member app (PLAN.md §5.2, §16.3 8.5, §20.2), as
 * on the phone app (mobile/src/components/RenewParts.tsx): a numbered step, a
 * plan or a way to pay to pick, the bar with the total and the next thing to
 * do, and the screens for waiting and done.
 */
import { useId } from "react";

import { t } from "@/i18n";
import { formatRs, formatWholeRs } from "@/lib/money";
import { Money } from "@/components/ui/Money";
import type { AccountKind, PaymentMethodAccount, Plan } from "@shared/types";
import { WALLET_BADGES } from "@shared/walletBadges";

// --- steps -----------------------------------------------------------------------

/** A numbered step of the page; a tick once it's done, faded until it's reached. */
export function Step({
  n,
  title,
  done,
  reached = true,
  children,
}: {
  n: number;
  title: string;
  done: boolean;
  reached?: boolean;
  children?: React.ReactNode;
}) {
  const id = useId();
  return (
    <section
      aria-labelledby={id}
      className={`space-y-3 transition-opacity ${reached ? "" : "opacity-45"}`}
    >
      <h2
        id={id}
        className="flex items-center gap-2.5 text-[1.0625rem] font-semibold text-slate-900"
      >
        <span
          aria-hidden
          className={`flex size-6.5 shrink-0 items-center justify-center rounded-full text-[0.8125rem] font-bold ${
            done
              ? "bg-brand-600 text-white"
              : reached
                ? "bg-brand-50 text-brand-700"
                : "bg-slate-100 text-slate-400"
          }`}
        >
          {done ? "✓" : n}
        </span>
        {title}
      </h2>
      {children}
    </section>
  );
}

// --- choosing --------------------------------------------------------------------

function Radio({ on }: { on: boolean }) {
  return (
    <span
      aria-hidden
      className={`flex size-5.5 shrink-0 items-center justify-center rounded-full border-2 ${
        on ? "border-brand-600" : "border-slate-300"
      }`}
    >
      {on && <span className="size-3 rounded-full bg-brand-600" />}
    </span>
  );
}

/** A card with a real radio button in it: arrow keys move through the group. */
function Option({
  name,
  label,
  checked,
  onChange,
  children,
}: {
  name: string;
  label: string;
  checked: boolean;
  onChange: () => void;
  children: React.ReactNode;
}) {
  return (
    <label
      className={`flex min-h-16 cursor-pointer items-center gap-3 rounded-2xl px-4 py-3.5 transition-[box-shadow,background-color] has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-brand-500 ${
        checked
          ? "bg-brand-50/70 ring-2 ring-brand-600"
          : "bg-surface shadow-card ring-1 ring-hairline hover:ring-slate-300"
      }`}
    >
      <input
        type="radio"
        name={name}
        aria-label={label}
        className="sr-only"
        checked={checked}
        onChange={onChange}
      />
      <Radio on={checked} />
      {children}
    </label>
  );
}

function Pill({
  children,
  className,
}: {
  children: React.ReactNode;
  className: string;
}) {
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-[0.6875rem] font-bold tracking-wide ${className}`}
    >
      {children}
    </span>
  );
}

/** One plan: its name and what it gives, the price, and what it saves. */
export function PlanOption({
  plan,
  checked,
  onChange,
  monthly,
  saved,
  best,
}: {
  plan: Plan;
  checked: boolean;
  onChange: () => void;
  monthly: number | null;
  saved: number | null;
  best: boolean;
}) {
  const extras = [
    plan.seats > 1 ? t("plans.forPeople", { count: plan.seats }) : null,
    monthly !== null && (plan.duration_months ?? 0) > 1
      ? t("app.renew.perMonth", { amount: formatWholeRs(monthly) })
      : null,
  ].filter(Boolean);
  return (
    <Option
      name="plan"
      // As on the phone: "1 month, Rs 2,500".
      label={`${plan.name}, ${formatRs(plan.price)}`}
      checked={checked}
      onChange={onChange}
    >
      <span className="min-w-0 flex-1 space-y-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-slate-900">{plan.name}</span>
          {best && (
            <Pill className="bg-brand-600 text-white">{t("app.renew.bestValue")}</Pill>
          )}
        </span>
        {extras.length > 0 && (
          <span className="block text-[0.8125rem] text-slate-500">
            {extras.join(" · ")}
          </span>
        )}
      </span>
      <span className="shrink-0 space-y-1 text-right">
        <Money
          paisa={plan.price}
          className="block text-[1.0625rem] font-bold text-slate-900"
        />
        {saved !== null && (
          <span className="block text-xs font-semibold text-emerald-700">
            {t("app.renew.saveShort", { amount: formatWholeRs(saved) })}
          </span>
        )}
      </span>
    </Option>
  );
}

export function WalletBadge({ kind, size = 40 }: { kind: AccountKind; size?: number }) {
  const badge = WALLET_BADGES[kind] ?? WALLET_BADGES.other;
  return (
    <span
      aria-hidden
      className="flex shrink-0 items-center justify-center font-bold text-white"
      style={{
        width: size,
        height: size,
        borderRadius: size / 4,
        fontSize: size * 0.45,
        backgroundColor: badge.color,
      }}
    >
      {badge.letter}
    </span>
  );
}

/** One of the gym's accounts: confirmed by the wallet itself, or by QR. */
export function MethodOption({
  method,
  checked,
  onChange,
}: {
  method: PaymentMethodAccount;
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <Option name="method" label={method.label} checked={checked} onChange={onChange}>
      <WalletBadge kind={method.kind} />
      <span className="min-w-0 flex-1 space-y-1">
        <span className="block font-semibold text-slate-900">{method.label}</span>
        {method.online ? (
          <Pill className="bg-emerald-50 text-emerald-700">
            {t("app.renew.instant")}
          </Pill>
        ) : (
          <span className="block text-[0.8125rem] text-slate-500">
            {t("app.renew.byQr")}
          </span>
        )}
      </span>
    </Option>
  );
}

// --- the bar ---------------------------------------------------------------------

/** The total and the one thing to do next, always in reach above the tabs. */
export function CheckoutBar({
  total,
  caption,
  children,
}: {
  total: number | null;
  caption: string;
  children: React.ReactNode;
}) {
  return (
    <>
      {/* Room for the bar, so the end of the page isn't under it. */}
      <div aria-hidden className="h-20" />
      <div className="fixed inset-x-0 bottom-[var(--tab-bar,4rem)] z-10 mx-auto flex max-w-md items-center gap-4 border-t border-hairline bg-surface px-4 py-3 shadow-[0_-4px_16px_rgba(15,23,42,0.06)]">
        <div className="max-w-[45%] min-w-23" aria-live="polite">
          <p className="truncate text-xs text-slate-500">{caption}</p>
          {total !== null ? (
            <Money paisa={total} className="block text-xl font-bold text-slate-900" />
          ) : (
            <p className="text-xl font-bold text-slate-400">—</p>
          )}
        </div>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </>
  );
}

// --- whole-page states -----------------------------------------------------------

/** Waiting or done: one clear message and what can be done next. */
export function StatusPanel({
  tone,
  title,
  note,
  lines,
  children,
}: {
  tone: "waiting" | "done";
  title: string;
  note?: string;
  lines: { label: string; value: string }[];
  children?: React.ReactNode;
}) {
  return (
    <div className="space-y-4 rounded-3xl bg-surface p-6 text-center shadow-card ring-1 ring-hairline">
      <p
        aria-hidden
        className={`mx-auto flex size-18 items-center justify-center rounded-full text-3xl font-bold ${
          tone === "done" ? "bg-emerald-50 text-emerald-600" : "bg-amber-50"
        }`}
      >
        {tone === "done" ? "✓" : "⏳"}
      </p>
      <h1 className="text-xl font-bold tracking-tight text-slate-900">{title}</h1>
      {note && <p className="text-sm text-slate-600">{note}</p>}
      {lines.length > 0 && (
        <dl className="space-y-2 pt-1 text-left text-sm">
          {lines.map((line) => (
            <div key={line.label} className="flex justify-between gap-3">
              <dt className="text-slate-500">{line.label}</dt>
              <dd className="text-right font-medium text-slate-900">{line.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {children && <div className="space-y-2 pt-1">{children}</div>}
    </div>
  );
}
