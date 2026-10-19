"use client";

import {
  CircleCheck,
  Inbox,
  MessageSquare,
  Phone,
  ScanLine,
  UserPlus,
  UserX,
  Wallet,
} from "lucide-react";
import Link from "next/link";

import { BarChart } from "@/components/charts/BarChart";
import { WhatsAppButton, WhatsAppLink } from "@/components/member/WhatsApp";
import { methodLabel } from "@/components/money/PaymentFields";
import { Notice } from "@/components/Notice";
import { Delta } from "@/components/today/Delta";
import { SetupChecklist } from "@/components/today/SetupChecklist";
import { Card, EmptyState, PageHeader, Stat } from "@/components/ui/Card";
import { Money } from "@/components/ui/Money";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { plural, t, type MessageKey } from "@/i18n";
import { errorMessage, messagesApi, reportsApi, type TodayData } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLive } from "@/lib/live";
import { formatRs } from "@/lib/money";
import { memberAppUrl } from "@/lib/slug";
import { useLoad } from "@/lib/useLoad";

// The hours a gym is usually open; any visit outside them widens the chart.
const OPEN_FROM = 5;
const OPEN_UNTIL = 21;

function hourLabel(hour: number): string {
  const twelve = hour % 12 === 0 ? 12 : hour % 12;
  return `${twelve}${hour < 12 ? "am" : "pm"}`;
}

function QuickAction({
  href,
  icon: Icon,
  label,
  primary,
}: {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  primary?: boolean;
}) {
  return (
    <Link
      href={href}
      className={`inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition ${
        primary
          ? "bg-brand-600 text-white shadow-brand hover:bg-brand-700"
          : "bg-white text-slate-800 shadow-card ring-1 ring-hairline hover:bg-slate-50"
      }`}
    >
      <Icon className="size-4" aria-hidden />
      {label}
    </Link>
  );
}

/** What needs someone's attention now, each with the button that does it. */
function ToDo({ data }: { data: TodayData }) {
  const { can } = useAuth();
  const toast = useToast();
  const pending = data.pending_requests ?? 0;
  const empty =
    pending === 0 &&
    data.ending_today.length === 0 &&
    data.top_owing.length === 0 &&
    data.turned_away.length === 0 &&
    data.not_visiting === 0 &&
    !data.leads_due;

  async function remind(memberId: string, name: string) {
    try {
      await messagesApi.smsMember(memberId, { reminder: true });
      toast.success(t("today.reminded", { name }));
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  const row = "flex items-center justify-between gap-3 py-2.5";
  const button =
    "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-brand-700 transition hover:bg-brand-50";

  return (
    <Card title={t("today.todo")}>
      {empty ? (
        <div className="flex items-center gap-2 py-4 text-sm text-slate-500">
          <CircleCheck className="size-5 text-emerald-600" aria-hidden />
          {t("today.nothingToDo")}
        </div>
      ) : (
        <div className="divide-y divide-hairline">
          {pending > 0 && (
            <div className={row}>
              <span className="flex items-center gap-2 text-sm font-medium text-slate-900">
                <Inbox className="size-4 text-red-600" aria-hidden />
                {t("today.requestsWaiting", { count: pending })}
              </span>
              <Link href="/staff/payment-requests" className={button}>
                {t("requests.approve")}
              </Link>
            </div>
          )}
          {data.leads_due_list.length > 0 && (
            <div className="py-2.5">
              <p className="flex justify-between pb-1 text-xs font-semibold tracking-wide text-slate-500 uppercase">
                {t("today.leadsDue", { count: data.leads_due ?? 0 })}
                <Link href="/staff/enquiries" className="normal-case text-brand-700">
                  {t("today.seeAll")}
                </Link>
              </p>
              <ul>
                {data.leads_due_list.map((l) => (
                  <li
                    key={l.lead_id}
                    className="flex items-center justify-between gap-2 py-1"
                  >
                    <span className="min-w-0 truncate text-sm font-medium text-slate-900">
                      {l.name}
                    </span>
                    {l.phone && (
                      <span className="flex shrink-0">
                        <a href={`tel:${l.phone}`} className={button}>
                          <Phone className="size-3.5" aria-hidden />
                          {t("today.call")}
                        </a>
                        <WhatsAppLink
                          phone={l.phone}
                          className={button}
                          iconClassName="size-3.5"
                        />
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {data.not_visiting > 0 && (
            <div className={row}>
              <span className="flex items-center gap-2 text-sm font-medium text-slate-900">
                <UserX className="size-4 text-amber-600" aria-hidden />
                {data.not_visiting === 1
                  ? t("today.notVisitingOne")
                  : t("today.notVisiting", { count: data.not_visiting })}
              </span>
              <Link href="/staff/follow-up?tab=not-visiting" className={button}>
                {t("today.seeWho")}
              </Link>
            </div>
          )}
          {data.ending_today.length > 0 && (
            <div className="py-2.5">
              <p className="pb-1 text-xs font-semibold tracking-wide text-slate-500 uppercase">
                {t("today.endingToday", { count: data.due_today })}
              </p>
              <ul>
                {data.ending_today.map((m) => (
                  <li
                    key={m.member_id}
                    className="flex items-center justify-between gap-2 py-1"
                  >
                    <Link
                      href={`/staff/members/${m.member_id}`}
                      className="min-w-0 truncate text-sm font-medium text-slate-900 hover:underline"
                    >
                      {m.name}
                    </Link>
                    <span className="flex shrink-0">
                      <a href={`tel:${m.phone}`} className={button}>
                        <Phone className="size-3.5" aria-hidden />
                        {t("today.call")}
                      </a>
                      <WhatsAppButton
                        memberId={m.member_id}
                        purpose="reminder"
                        className={button}
                        iconClassName="size-3.5"
                      />
                      {can("messages.sms") && (
                        <button
                          type="button"
                          className={button}
                          onClick={() => void remind(m.member_id, m.name)}
                        >
                          <MessageSquare className="size-3.5" aria-hidden />
                          {t("today.remind")}
                        </button>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {data.top_owing.length > 0 && (
            <div className="py-2.5">
              <p className="pb-1 text-xs font-semibold tracking-wide text-slate-500 uppercase">
                {t("today.owing", { count: data.members_with_dues })}
              </p>
              <ul>
                {data.top_owing.map((m) => (
                  <li
                    key={m.member_id}
                    className="flex items-center justify-between gap-2 py-1"
                  >
                    <Link
                      href={`/staff/members/${m.member_id}`}
                      className="min-w-0 truncate text-sm font-medium text-slate-900 hover:underline"
                    >
                      {m.name}
                    </Link>
                    <span className="flex shrink-0 items-center gap-2">
                      <Money paisa={m.dues} className="text-sm text-amber-700" />
                      {can("payments.collect") && (
                        <Link href={`/staff/members/${m.member_id}`} className={button}>
                          {t("payment.collect")}
                        </Link>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {data.turned_away.length > 0 && (
            <div className="py-2.5">
              <p className="pb-1 text-xs font-semibold tracking-wide text-red-700 uppercase">
                {t("today.turnedAway")}
              </p>
              <ul>
                {data.turned_away.map((p) => (
                  <li key={`${p.member_id}-${p.at}`} className="py-1 text-sm">
                    <Link
                      href={`/staff/members/${p.member_id}`}
                      className="font-medium text-slate-900 hover:underline"
                    >
                      {p.name}
                    </Link>{" "}
                    <span className="text-slate-500">
                      · {t(`door.result.${p.result}` as MessageKey)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

/** Today (PLAN.md §7, §16.2 7.4): what to do now, and how the day is going. */
export default function TodayPage() {
  const { me, can } = useAuth();
  const { display } = useGymCalendar();
  const { data, error, reload } = useLoad(
    () => (me?.gym && can("members.view") ? reportsApi.today() : Promise.resolve(null)),
    [me?.gym?.id],
  );
  // Who's inside, what came in, who's waiting: as it happens.
  useLive(["check_in", "member", "payment_request"], reload, { everyMs: 3000 });
  if (!me) return null;
  if (!me.gym) return <Notice>{t("staff.platformAdmin")}</Notice>;

  const hours = data?.check_ins_by_hour ?? [];
  const first = Math.min(OPEN_FROM, ...hours.flatMap((n, h) => (n ? [h] : [])));
  const last = Math.max(OPEN_UNTIL, ...hours.flatMap((n, h) => (n ? [h] : [])));
  const shownHours = Array.from({ length: last - first + 1 }, (_, i) => first + i);

  return (
    <div className="space-y-4">
      <PageHeader
        title={t("staff.welcome", { name: me.staff.name.split(" ")[0] })}
        subtitle={data ? formatDate(data.date, display) : undefined}
        actions={
          <>
            {can("members.add") && (
              <QuickAction
                href="/staff/members/new"
                icon={UserPlus}
                label={t("members.add")}
                primary
              />
            )}
            {can("door.check_in") && (
              <QuickAction href="/staff/door" icon={ScanLine} label={t("today.scan")} />
            )}
            {can("payments.collect") && can("members.view") && (
              <QuickAction
                href="/staff/members?filter=dues"
                icon={Wallet}
                label={t("payment.collect")}
              />
            )}
          </>
        }
      />
      {error && <Notice tone="error">{error}</Notice>}
      {!can("members.view") && (
        <Notice>{t("staff.memberAppAt", { url: memberAppUrl(me.gym.slug) })}</Notice>
      )}
      {!data && !error && can("members.view") && (
        <PageSkeleton label={t("common.loading")} />
      )}
      {data && (
        <>
          {data.setup && <SetupChecklist steps={data.setup} onDismissed={reload} />}

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat
              value={data.check_ins}
              label={t("today.checkIns")}
              href="/staff/attendance"
              hint={<Delta now={data.check_ins} before={data.check_ins_yesterday} />}
            />
            {data.collected !== null && (
              <Stat
                value={<Money paisa={data.collected} />}
                label={t("today.collected")}
                href="/staff/payments"
                hint={
                  <Delta
                    now={data.collected}
                    before={data.collected_yesterday ?? 0}
                    format={(paisa) => formatRs(paisa)}
                  />
                }
              />
            )}
            <Stat
              value={data.active_members}
              label={t("today.active")}
              href="/staff/members"
              hint={
                data.expiring_this_week === 0
                  ? t("today.endingThisWeekNone")
                  : plural(
                      data.expiring_this_week,
                      "today.endingThisWeekOne",
                      "today.endingThisWeek",
                    )
              }
            />
            <Stat
              value={<Money paisa={data.dues_total} />}
              label={plural(data.members_with_dues, "today.duesOne", "today.dues")}
              tone={data.dues_total ? "warning" : "plain"}
              href="/staff/members?filter=dues"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-5">
            <div className="min-w-0 lg:col-span-3">
              <ToDo data={data} />
            </div>
            <div className="min-w-0 space-y-4 lg:col-span-2">
              <Card title={t("today.byHour")}>
                <BarChart
                  title={t("today.byHour")}
                  labels={shownHours.map(hourLabel)}
                  series={[
                    {
                      key: "check_ins",
                      label: t("today.checkIns"),
                      values: shownHours.map((h) => hours[h] ?? 0),
                    },
                  ]}
                  height={150}
                  everyNthLabel={3}
                />
              </Card>
              <Card title={t("today.insideNow")}>
                {data.inside_now.length === 0 && (
                  <EmptyState title={t("followUp.none")} />
                )}
                <ul className="divide-y divide-hairline text-sm">
                  {data.inside_now.map((p) => (
                    <li key={p.member_id} className="flex justify-between py-2">
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
              {data.collected_by_method &&
                Object.keys(data.collected_by_method).length > 0 && (
                  <Card title={t("today.collected")}>
                    <dl className="divide-y divide-hairline text-sm">
                      {Object.entries(data.collected_by_method).map(
                        ([method, amount]) => (
                          <div key={method} className="flex justify-between py-2">
                            <dt>{methodLabel(method)}</dt>
                            <dd className="font-semibold">
                              <Money paisa={amount} />
                            </dd>
                          </div>
                        ),
                      )}
                    </dl>
                  </Card>
                )}
            </div>
          </div>
          <p className="pt-1 text-sm text-slate-500">
            {t("staff.memberAppAt", { url: memberAppUrl(me.gym.slug) })}
          </p>
        </>
      )}
    </div>
  );
}
