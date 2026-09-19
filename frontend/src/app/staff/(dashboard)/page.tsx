"use client";

import Link from "next/link";

import { methodLabel } from "@/components/money/PaymentFields";
import { Notice } from "@/components/Notice";
import { Card, PageHeader } from "@/components/ui/Card";
import { Money } from "@/components/ui/Money";
import { t, type MessageKey } from "@/i18n";
import { reportsApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { memberAppUrl } from "@/lib/slug";
import { useLoad } from "@/lib/useLoad";

function Stat({
  value,
  label,
  href,
  tone = "",
}: {
  value: React.ReactNode;
  label: string;
  href?: string;
  tone?: string;
}) {
  const body = (
    <div
      className={`rounded-xl border border-slate-200 bg-white p-4 ${href ? "hover:border-brand-600" : ""}`}
    >
      <p className={`text-3xl font-bold ${tone}`}>{value}</p>
      <p className="text-sm text-slate-600">{label}</p>
    </div>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

/** Today (PLAN.md §7): who's in, who's due, who was turned away, what came in. */
export default function TodayPage() {
  const { me, can } = useAuth();
  const { display } = useGymCalendar();
  const { data, error } = useLoad(
    () => (me?.gym && can("members.view") ? reportsApi.today() : Promise.resolve(null)),
    [me?.gym?.id],
  );
  if (!me) return null;
  if (!me.gym) return <Notice>{t("staff.platformAdmin")}</Notice>;

  return (
    <div className="space-y-4">
      <PageHeader
        title={t("staff.welcome", { name: me.staff.name.split(" ")[0] })}
        subtitle={data ? formatDate(data.date, display) : undefined}
      />
      {error && <Notice tone="error">{error}</Notice>}
      {!can("members.view") && (
        <Notice>{t("staff.memberAppAt", { url: memberAppUrl(me.gym.slug) })}</Notice>
      )}
      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat
              value={data.check_ins}
              label={t("today.checkIns")}
              href="/staff/attendance"
            />
            <Stat value={data.inside_now.length} label={t("today.inside")} />
            <Stat
              value={data.due_today}
              label={t("today.dueToday")}
              href="/staff/expiring"
              tone={data.due_today ? "text-amber-700" : ""}
            />
            <Stat
              value={data.expiring_this_week}
              label={t("today.dueWeek")}
              href="/staff/expiring"
            />
            <Stat
              value={data.active_members}
              label={t("today.active")}
              href="/staff/members"
            />
            <Stat
              value={<Money paisa={data.dues_total} />}
              label={t("today.dues", { count: data.members_with_dues })}
              tone={data.dues_total ? "text-amber-700" : ""}
            />
            {data.collected !== null && (
              <Stat
                value={<Money paisa={data.collected} />}
                label={t("today.collected")}
                href="/staff/payments"
              />
            )}
            {data.pending_requests !== null && (
              <Stat
                value={data.pending_requests}
                label={t("nav.requests")}
                href="/staff/payment-requests"
                tone={data.pending_requests ? "text-red-600" : ""}
              />
            )}
          </div>

          {data.turned_away.length > 0 && (
            <Card title={t("today.turnedAway")} className="border-red-200 bg-red-50">
              <ul className="space-y-1 text-sm">
                {data.turned_away.map((p) => (
                  <li key={`${p.member_id}-${p.at}`}>
                    <Link
                      href={`/staff/members/${p.member_id}`}
                      className="font-medium hover:underline"
                    >
                      {p.name}
                    </Link>{" "}
                    <span className="text-slate-600">
                      · {t(`door.result.${p.result}` as MessageKey)} ·{" "}
                      {formatDateTime(p.at, display)}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            <Card title={t("today.insideNow")}>
              {data.inside_now.length === 0 && (
                <p className="text-sm text-slate-500">{t("expiring.none")}</p>
              )}
              <ul className="space-y-1 text-sm">
                {data.inside_now.map((p) => (
                  <li key={p.member_id} className="flex justify-between">
                    <Link
                      href={`/staff/members/${p.member_id}`}
                      className="hover:underline"
                    >
                      {p.name}
                    </Link>
                    <span className="text-slate-500">
                      {formatDateTime(p.at, display).split(", ")[1]}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-slate-500">{t("today.insideHelp")}</p>
            </Card>
            {data.collected_by_method && (
              <Card title={t("today.collected")}>
                {Object.keys(data.collected_by_method).length === 0 && (
                  <p className="text-sm text-slate-500">{t("payment.none")}</p>
                )}
                <dl className="space-y-1 text-sm">
                  {Object.entries(data.collected_by_method).map(([method, amount]) => (
                    <div key={method} className="flex justify-between">
                      <dt>{methodLabel(method)}</dt>
                      <dd className="font-semibold">
                        <Money paisa={amount} />
                      </dd>
                    </div>
                  ))}
                </dl>
              </Card>
            )}
          </div>
          <p className="text-sm text-slate-500">
            {t("staff.memberAppAt", { url: memberAppUrl(me.gym.slug) })}
          </p>
        </>
      )}
    </div>
  );
}
