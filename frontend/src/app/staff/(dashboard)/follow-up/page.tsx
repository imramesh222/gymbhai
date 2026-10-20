"use client";

import { MessageSquare, Phone } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { SendSms } from "@/components/member/SendSms";
import { WhatsAppButton } from "@/components/member/WhatsApp";
import { Notice } from "@/components/Notice";
import { Card, EmptyState, PageHeader } from "@/components/ui/Card";
import { Money } from "@/components/ui/Money";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { Tabs, useTab, type Tab } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/Toast";
import { t, type MessageKey } from "@/i18n";
import {
  messagesApi,
  type FollowUpLists,
  type Member,
  type MessagePurpose,
  type PtOwing,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { daysBetween, todayInNepal } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLive } from "@/lib/live";
import { useLoad } from "@/lib/useLoad";

type TabId = "ending" | "lapsed" | "owing" | "not-visiting";

/** Who a "Send message" is for. */
type Recipient = { id: string; name: string };
type OnMessage = (to: Recipient, reminder: boolean) => void;

const BUTTON =
  "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-semibold text-brand-700 transition hover:bg-brand-50";

function lastVisit(member: Member): string {
  if (!member.last_visit_at) return t("followUp.neverVisited");
  const days = daysBetween(
    todayInNepal(new Date(member.last_visit_at)),
    todayInNepal(),
  );
  if (days === 0) return t("followUp.visitedToday");
  return days === 1
    ? t("followUp.visitedDayAgo")
    : t("followUp.visitedDaysAgo", { count: days });
}

/** Call, WhatsApp and Send message, beside each row. */
function Actions({
  to,
  phone,
  reminder,
  purpose,
  onMessage,
}: {
  to: Recipient;
  phone: string;
  reminder: boolean;
  /** What a WhatsApp message to them says (§18.5). */
  purpose: MessagePurpose;
  onMessage: OnMessage;
}) {
  const { can } = useAuth();
  return (
    <span className="flex shrink-0">
      <a href={`tel:${phone}`} className={BUTTON}>
        <Phone className="size-4" aria-hidden />
        {t("followUp.call")}
      </a>
      <WhatsAppButton memberId={to.id} purpose={purpose} className={BUTTON} />
      {can("messages.sms") && (
        <button
          type="button"
          className={BUTTON}
          onClick={() => onMessage(to, reminder)}
        >
          <MessageSquare className="size-4" aria-hidden />
          {t("followUp.message")}
        </button>
      )}
    </span>
  );
}

function Row({
  member,
  reminder,
  purpose,
  onMessage,
}: {
  member: Member;
  reminder: boolean;
  purpose: MessagePurpose;
  onMessage: OnMessage;
}) {
  const { date } = useGymCalendar();
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 py-2.5">
      <Link href={`/staff/members/${member.id}`} className="min-w-0 hover:underline">
        <p className="truncate font-medium">{member.name}</p>
        <p className="text-xs text-slate-500">
          {member.current?.plan_name ?? t("followUp.noPlan")}
          {member.valid_until && <> · {date(member.valid_until)}</>}
          {" · "}
          {lastVisit(member)}
          {member.dues > 0 && (
            <>
              {" · "}
              <span className="text-amber-700">
                {t("members.owes")} <Money paisa={member.dues} />
              </span>
            </>
          )}
        </p>
      </Link>
      <Actions
        to={member}
        phone={member.phone}
        reminder={reminder}
        purpose={purpose}
        onMessage={onMessage}
      />
    </li>
  );
}

/** Owed on personal training (§18.3): each package, with its plan and trainer. */
function PtSection({
  rows,
  total,
  onMessage,
}: {
  rows: PtOwing[];
  total: number;
  onMessage: OnMessage;
}) {
  const { date } = useGymCalendar();
  return (
    <Card title={`${t("followUp.owingPt")} (${total})`}>
      <ul className="divide-y divide-hairline">
        {rows.map((row) => (
          <li
            key={row.package_id}
            className="flex flex-wrap items-center justify-between gap-2 py-2.5"
          >
            <Link
              href={`/staff/members/${row.member_id}?tab=training`}
              className="min-w-0 hover:underline"
            >
              <p className="truncate font-medium">{row.name}</p>
              <p className="text-xs text-slate-500">
                {t("followUp.ptRow", {
                  plan: row.plan_name,
                  trainer: row.trainer_name,
                  date: date(row.end_date),
                })}
                {" · "}
                <span className="text-amber-700">
                  {t("members.owes")} <Money paisa={row.dues} />
                </span>
              </p>
            </Link>
            <Actions
              to={{ id: row.member_id, name: row.name }}
              phone={row.phone}
              reminder={false}
              purpose="pt_dues"
              onMessage={onMessage}
            />
          </li>
        ))}
      </ul>
      {total > rows.length && (
        <p className="pt-3 text-sm text-slate-500">
          {t("followUp.showingFirst", { shown: rows.length, total })}
        </p>
      )}
    </Card>
  );
}

function Section({
  title,
  members,
  reminder,
  purpose,
  onMessage,
  more,
}: {
  title?: string;
  members: Member[];
  reminder: boolean;
  purpose: MessagePurpose;
  onMessage: OnMessage;
  /** Shown under a list that was cut short. */
  more?: React.ReactNode;
}) {
  return (
    <Card title={title}>
      {members.length === 0 ? (
        <EmptyState title={t("followUp.none")} />
      ) : (
        <ul className="divide-y divide-hairline">
          {members.map((m) => (
            <Row
              key={m.id}
              member={m}
              reminder={reminder}
              purpose={purpose}
              onMessage={onMessage}
            />
          ))}
        </ul>
      )}
      {more}
    </Card>
  );
}

function Panel({
  tab,
  data,
  onMessage,
}: {
  tab: TabId;
  data: FollowUpLists;
  onMessage: OnMessage;
}) {
  const { can } = useAuth();
  const cut = (shown: number, total: number, filter: string) =>
    total > shown ? (
      <p className="pt-3 text-sm text-slate-500">
        {t("followUp.showingFirst", { shown, total })}{" "}
        <Link
          href={`/staff/members?filter=${filter}`}
          className="font-medium text-brand-700 hover:underline"
        >
          {t("followUp.seeAll")}
        </Link>
      </p>
    ) : undefined;

  if (tab === "ending")
    return (
      <div className="space-y-4">
        <Section
          title={`${t("followUp.today")} (${data.due_today.length})`}
          members={data.due_today}
          reminder
          purpose="reminder"
          onMessage={onMessage}
        />
        <Section
          title={`${t("followUp.week")} (${data.due_this_week.length})`}
          members={data.due_this_week}
          reminder
          purpose="reminder"
          onMessage={onMessage}
        />
      </div>
    );
  if (tab === "lapsed")
    return (
      <Section
        members={data.lapsed}
        reminder
        purpose="reminder"
        onMessage={onMessage}
      />
    );
  if (tab === "owing") {
    const memberships = (
      <Section
        title={
          data.pt_owing_total > 0
            ? `${t("followUp.owingMemberships")} (${data.owing_total})`
            : undefined
        }
        members={data.owing}
        reminder={false}
        purpose="dues"
        onMessage={onMessage}
        more={cut(data.owing.length, data.owing_total, "dues")}
      />
    );
    // Personal training's dues are its own (§18.3): a list of their own.
    if (data.pt_owing_total === 0) return memberships;
    return (
      <div className="space-y-4">
        {memberships}
        <PtSection
          rows={data.pt_owing}
          total={data.pt_owing_total}
          onMessage={onMessage}
        />
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600">
        {t("followUp.notVisitingHelp", { days: data.not_visiting_days })}{" "}
        {can("setup.check_in_rules") && (
          <Link
            href="/staff/settings/check-in"
            className="font-medium text-brand-700 hover:underline"
          >
            {t("followUp.change")}
          </Link>
        )}
      </p>
      <Section
        members={data.not_visiting}
        reminder={false}
        purpose="not_visiting"
        onMessage={onMessage}
        more={cut(data.not_visiting.length, data.not_visiting_total, "not_visiting")}
      />
    </div>
  );
}

/** Who to chase (PLAN.md §7, §16.3 8.1), one tab per reason. */
export default function FollowUpPage() {
  const toast = useToast();
  const { data, error, reload } = useLoad(() => messagesApi.followUp(), []);
  // A visit, a payment or a renewal can take someone off a list.
  useLive(["check_in", "member"], reload, { everyMs: 5000 });
  const [messaging, setMessaging] = useState<{
    to: Recipient;
    reminder: boolean;
  } | null>(null);

  const tabs: (Tab & { id: TabId })[] = [
    {
      id: "ending",
      label: t("followUp.tab.ending"),
      count: data ? data.due_today.length + data.due_this_week.length : undefined,
    },
    { id: "lapsed", label: t("followUp.tab.lapsed"), count: data?.lapsed.length },
    {
      id: "owing",
      label: t("followUp.tab.owing"),
      count: data ? data.owing_total + data.pt_owing_total : undefined,
    },
    {
      id: "not-visiting",
      label: t("followUp.tab.notVisiting"),
      count: data?.not_visiting_total,
    },
  ];
  const tab = useTab(tabs) as TabId;
  const subtitles: Record<TabId, MessageKey> = {
    ending: "followUp.subtitle.ending",
    lapsed: "followUp.subtitle.lapsed",
    owing: "followUp.subtitle.owing",
    "not-visiting": "followUp.subtitle.notVisiting",
  };

  return (
    <div className="space-y-4">
      <PageHeader title={t("followUp.title")} subtitle={t(subtitles[tab])} />
      {error && <Notice tone="error">{error}</Notice>}
      <Tabs tabs={tabs} label={t("followUp.title")}>
        {data ? (
          <Panel
            tab={tab}
            data={data}
            onMessage={(to, reminder) => setMessaging({ to, reminder })}
          />
        ) : (
          !error && <PageSkeleton label={t("common.loading")} />
        )}
      </Tabs>
      {messaging && (
        <SendSms
          memberId={messaging.to.id}
          reminder={messaging.reminder}
          onClose={() => setMessaging(null)}
          onSent={() => {
            toast.success(t("followUp.sent", { name: messaging.to.name }));
            setMessaging(null);
          }}
        />
      )}
    </div>
  );
}
