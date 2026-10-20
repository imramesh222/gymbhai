"use client";

import {
  Archive,
  CreditCard,
  IdCard,
  KeyRound,
  LogOut,
  MessageCircle,
  MessageSquare,
  Pencil,
  QrCode,
  Send,
  Smartphone,
  Snowflake,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useRef, useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { CollectPayment } from "@/components/member/CollectPayment";
import { EditMember } from "@/components/member/EditMember";
import { EraseMember } from "@/components/member/EraseMember";
import { History } from "@/components/member/History";
import { PaymentsTable } from "@/components/member/PaymentsTable";
import { SendSms } from "@/components/member/SendSms";
import { SignInQr } from "@/components/member/SignInQr";
import { WhatsAppDialog } from "@/components/member/WhatsApp";
import { VisitsCalendar } from "@/components/member/VisitsCalendar";
import { TrainingTab } from "@/components/training/TrainingTab";
import { Avatar } from "@/components/ui/Avatar";
import { Card, EmptyState, Row } from "@/components/ui/Card";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { Menu, type MenuItem } from "@/components/ui/Menu";
import { Money } from "@/components/ui/Money";
import { ListSkeleton } from "@/components/ui/Skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Tabs, useTab, type Tab } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/Toast";
import { t, type MessageKey } from "@/i18n";
import {
  accessApi,
  branchesApi,
  doorApi,
  errorMessage,
  membersApi,
  messagesApi,
  ptApi,
  type MemberDetail,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { shrinkImage } from "@/lib/image";
import { useLive } from "@/lib/live";
import { useLoad } from "@/lib/useLoad";

type DialogName = "pay" | "edit" | "sms" | "erase" | "signIn" | "whatsapp" | null;

function MembershipsList({ member }: { member: MemberDetail }) {
  const { date } = useGymCalendar();
  if (member.memberships.length === 0)
    return <EmptyState title={t("member.noMemberships")} />;
  return (
    <ul className="divide-y divide-hairline">
      {member.memberships.map((m) => (
        <li key={m.id}>
          <Link
            href={`/staff/memberships/${m.id}`}
            className="flex items-center justify-between gap-3 py-3 hover:bg-slate-50"
          >
            <div className="min-w-0">
              <p className="font-medium text-slate-900">{m.plan_name}</p>
              <p className="text-xs text-slate-500">
                {date(m.start_date)} → {date(m.end_date)}
                {m.visit_limit !== null &&
                  ` · ${t("membership.visitsUsed", {
                    used: m.visits_used ?? 0,
                    limit: m.visit_limit,
                  })}`}
              </p>
            </div>
            <div className="shrink-0 text-right">
              <StatusBadge status={m.status} />
              <p className="mt-1 text-xs text-slate-500">
                <Money paisa={m.paid} /> / <Money paisa={m.total} />
              </p>
              {m.dues > 0 && (
                <p className="text-xs font-medium text-amber-700">
                  {t("members.owes")} <Money paisa={m.dues} />
                </p>
              )}
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function Messages({ memberId }: { memberId: string }) {
  const { display } = useGymCalendar();
  const { data } = useLoad(() => messagesApi.smsLog(memberId), [memberId]);
  if (!data) return <ListSkeleton rows={3} />;
  if (data.items.length === 0) return <EmptyState title={t("member.noMessages")} />;
  return (
    <ul className="divide-y divide-hairline">
      {data.items.map((sms) => (
        <li key={sms.id} className="py-3">
          <p className="flex justify-between gap-3 text-xs text-slate-500">
            <span>
              {t(`sms.kind.${sms.kind}` as MessageKey)} ·{" "}
              {formatDateTime(sms.created_at, display)}
            </span>
            <span>{t(`sms.status.${sms.status}` as MessageKey)}</span>
          </p>
          <p className="mt-1 text-sm text-slate-800">{sms.body}</p>
        </li>
      ))}
    </ul>
  );
}

function HistoryTab({ memberId }: { memberId: string }) {
  const { data } = useLoad(() => membersApi.history(memberId), [memberId]);
  if (!data) return <ListSkeleton rows={3} />;
  return <History entries={data} />;
}

/**
 * A member (PLAN.md §7, §16.2 7.5): who they are and where they stand, the
 * day-to-day actions on top, the rest in More, and the detail in tabs.
 */
export default function MemberPage() {
  const { id } = useParams<{ id: string }>();
  const receipt = useSearchParams().get("receipt");
  const { can, me } = useAuth();
  const { date, display } = useGymCalendar();
  const toast = useToast();
  const confirm = useConfirm();
  const {
    data: member,
    error,
    reload,
    setData,
  } = useLoad(() => membersApi.get(id), [id]);
  // Personal training (PLAN.md §18.3): its own tab, its own money.
  const training = useLoad(() => ptApi.ofMember(id), [id]);
  const reloadAll = () => {
    reload();
    training.reload();
  };
  // Another desk took a payment, the door let them in, they renewed in the
  // app, or their trainer recorded a session.
  useLive(["member", "check_in"], reloadAll, {
    match: (event) => event.member === id,
  });
  const branches = useLoad(() => branchesApi.list(), []).data ?? [];
  const [dialog, setDialog] = useState<DialogName>(null);
  const photoInput = useRef<HTMLInputElement>(null);

  const tabs: Tab[] = [
    { id: "overview", label: t("member.tab.overview") },
    {
      id: "memberships",
      label: t("member.memberships"),
      count: member?.memberships.length,
    },
    ...(can("pt.sell") || (training.data?.length ?? 0) > 0
      ? [{ id: "training", label: t("pt.title"), count: training.data?.length }]
      : []),
    { id: "payments", label: t("member.payments"), count: member?.payments.length },
    { id: "visits", label: t("member.tab.visits") },
    ...(can("messages.sms")
      ? [{ id: "messages", label: t("member.tab.messages") }]
      : []),
    { id: "history", label: t("member.tab.history") },
  ];
  const tab = useTab(tabs);

  if (error) return <Notice tone="error">{error}</Notice>;
  if (!member) return <ListSkeleton />;

  const branchName = branches.find((b) => b.id === member.home_branch_id)?.name;
  // Erased at their request: nothing left to edit or contact.
  const erased = member.erased_at !== null;
  const current = member.memberships.find((m) => m.id === member.current?.id);

  async function act(action: () => Promise<unknown>, done: MessageKey) {
    try {
      await action();
      toast.success(t(done));
      reload();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  async function changePhoto(file: File | undefined) {
    if (!file) return;
    try {
      setData(await membersApi.uploadPhoto(member!.id, await shrinkImage(file)));
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  async function checkIn() {
    const branch =
      branches.find((b) => b.id === member!.home_branch_id)?.id ?? branches[0]?.id;
    if (!branch) return;
    try {
      const result = await doorApi.manual({ member_id: member!.id, branch_id: branch });
      const outcome = t(`door.result.${result.result}` as MessageKey);
      if (result.let_in) toast.success(`${member!.name} — ${outcome}`);
      else toast.error(`${member!.name} — ${outcome}`);
      reload();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  const more: MenuItem[] = [
    {
      label: t("common.edit"),
      icon: Pencil,
      onSelect: () => setDialog("edit"),
      hidden: !can("members.edit"),
    },
    {
      label: t("member.freeze"),
      icon: Snowflake,
      href: current ? `/staff/memberships/${current.id}?do=freeze` : undefined,
      hidden: !can("memberships.freeze") || !current,
    },
    {
      label: t("whatsapp.title"),
      icon: MessageCircle,
      onSelect: () => setDialog("whatsapp"),
      hidden: erased,
    },
    {
      label: t("sms.send"),
      icon: MessageSquare,
      onSelect: () => setDialog("sms"),
      hidden: !can("messages.sms"),
    },
    {
      label: t("access.printCard"),
      icon: IdCard,
      href: `/staff/members/${member.id}/card`,
      hidden: !can("members.edit"),
    },
    {
      label: member.app_access ? t("member.accessOff") : t("member.accessOn"),
      icon: KeyRound,
      hidden: !can("members.app_access"),
      onSelect: async () => {
        if (
          member.app_access &&
          !(await confirm({
            title: t("member.accessOff"),
            message: t("access.appAccessHelp"),
            confirmLabel: t("member.accessOff"),
            danger: true,
          }))
        )
          return;
        await act(
          () => accessApi.setAccess(member.id, !member.app_access),
          "common.saved",
        );
      },
    },
    {
      label: t("access.signInPhone"),
      icon: Smartphone,
      hidden:
        !can("members.app_access") ||
        !member.app_access ||
        member.is_archived ||
        erased,
      onSelect: () => setDialog("signIn"),
    },
    {
      label: t("access.resendWelcome"),
      icon: Send,
      hidden: !can("members.app_access"),
      onSelect: () =>
        act(() => accessApi.resendWelcome(member.id), "access.welcomeSent"),
    },
    {
      label: t("access.signOutAll"),
      icon: LogOut,
      hidden: !can("members.app_access"),
      onSelect: async () => {
        if (
          await confirm({
            title: t("access.signOutAll"),
            message: t("access.signOutConfirm"),
            confirmLabel: t("access.signOutAll"),
          })
        )
          await act(() => accessApi.signOutAll(member.id), "access.signedOut");
      },
    },
    {
      label: t("access.reissueQr"),
      icon: QrCode,
      hidden: !can("members.app_access"),
      onSelect: async () => {
        if (
          await confirm({
            title: t("access.reissueQr"),
            message: t("access.reissueConfirm"),
            confirmLabel: t("access.reissueQr"),
            danger: true,
          })
        )
          await act(() => accessApi.reissueQr(member.id), "access.qrReissued");
      },
    },
    {
      label: member.is_archived ? t("member.unarchive") : t("member.archive"),
      icon: Archive,
      hidden: !can("members.archive"),
      onSelect: async () => {
        if (member.is_archived)
          return act(() => membersApi.unarchive(member.id), "member.restored");
        if (
          await confirm({
            title: t("member.archive"),
            message: t("member.archiveConfirm"),
            confirmLabel: t("member.archive"),
          })
        )
          await act(() => membersApi.archive(member.id), "member.archivedDone");
      },
    },
    {
      label: t("erase.open"),
      icon: Trash2,
      danger: true,
      hidden: !me?.staff.is_owner,
      onSelect: () => setDialog("erase"),
    },
  ];

  return (
    <div className="space-y-4">
      {receipt && (
        <Notice tone="success">
          {t("member.saved")}{" "}
          <Link href={`/staff/receipts/${receipt}`} className="font-semibold underline">
            {t("payment.printReceipt")}
          </Link>
        </Notice>
      )}
      {erased && (
        <Notice>
          {t("erase.done", { date: date(member.erased_at!.slice(0, 10)) })}
        </Notice>
      )}

      <section className="rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 items-center gap-4">
            <button
              type="button"
              onClick={() =>
                can("members.edit") && !erased && photoInput.current?.click()
              }
              aria-label={t("member.changePhoto")}
              title={t("member.changePhoto")}
              className="shrink-0"
            >
              <Avatar name={member.name} url={member.photo_url} size="size-16" />
            </button>
            <div className="min-w-0">
              <h1 className="truncate text-2xl font-bold tracking-tight text-slate-900">
                {member.name}
              </h1>
              <p className="text-sm text-slate-500">
                {erased
                  ? member.member_code
                  : `${member.member_code} · ${member.phone}`}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                <StatusBadge
                  status={member.is_archived ? "cancelled" : member.status}
                />
                {member.is_archived && (
                  <span className="text-xs text-slate-500">{t("member.archived")}</span>
                )}
                {(member.status === "active" || member.status === "frozen") && (
                  <span className="font-semibold text-slate-900">
                    {member.days_left} {t("member.daysLeftLabel")}
                  </span>
                )}
                {member.dues > 0 && (
                  <span className="font-semibold text-amber-700">
                    {t("members.owes")} <Money paisa={member.dues} />
                  </span>
                )}
              </div>
            </div>
          </div>
          {!erased && (
            <div className="flex flex-wrap gap-2 print:hidden">
              {can("memberships.sell") && !member.is_archived && (
                <Link href={`/staff/members/${member.id}/renew`}>
                  <Button>
                    {member.status === "none" ? t("member.sell") : t("member.renew")}
                  </Button>
                </Link>
              )}
              {can("payments.collect") && member.dues > 0 && (
                <Button variant="secondary" onClick={() => setDialog("pay")}>
                  <CreditCard className="size-4" aria-hidden />
                  {t("payment.collect")}
                </Button>
              )}
              {can("door.check_in") && !member.is_archived && (
                <Button variant="secondary" onClick={() => void checkIn()}>
                  {t("palette.checkIn")}
                </Button>
              )}
              <Menu items={more} />
            </div>
          )}
        </div>
      </section>
      <input
        ref={photoInput}
        type="file"
        accept="image/*"
        capture="user"
        className="hidden"
        onChange={(e) => void changePhoto(e.target.files?.[0])}
      />

      <Tabs tabs={tabs} label={t("member.tabsLabel")}>
        {tab === "overview" && (
          <div className="grid gap-4 md:grid-cols-3">
            <Card title={t("member.current")} className="md:col-span-1">
              {member.current ? (
                <dl className="divide-y divide-hairline">
                  <Row label={t("member.plan")}>{member.current.plan_name}</Row>
                  {member.valid_until && (
                    <Row
                      label={
                        member.status === "expired"
                          ? t("member.expiredOn")
                          : t("member.validUntil")
                      }
                    >
                      {date(member.valid_until)}
                    </Row>
                  )}
                  <Row label={t("member.dues")}>
                    <Money
                      paisa={member.dues}
                      className={member.dues > 0 ? "text-amber-700" : ""}
                    />
                  </Row>
                </dl>
              ) : (
                <EmptyState title={t("member.noMemberships")} />
              )}
            </Card>
            <Card title={t("member.details")} className="md:col-span-2">
              <dl className="grid gap-x-6 sm:grid-cols-2">
                <Row label={t("member.email")}>{member.email ?? "—"}</Row>
                <Row label={t("member.homeBranch")}>{branchName ?? "—"}</Row>
                <Row label={t("member.joined")}>{date(member.joined_on)}</Row>
                <Row label={t("member.dateOfBirth")}>{date(member.date_of_birth)}</Row>
                <Row label={t("member.address")}>{member.address ?? "—"}</Row>
                <Row label={t("member.emergencyContact")}>
                  {member.emergency_contact ?? "—"}
                </Row>
                {member.referred_by_id && (
                  <Row label={t("leads.referredBy")}>
                    <Link
                      href={`/staff/members/${member.referred_by_id}`}
                      className="text-brand-700 hover:underline"
                    >
                      {member.referred_by_name}
                    </Link>
                  </Row>
                )}
                <Row label={t("access.appAccess")}>
                  {member.app_access
                    ? t("member.accessOnShort")
                    : t("member.accessOffShort")}
                  {member.app_signed_in_at && (
                    <span className="block text-xs font-normal text-slate-500">
                      {t("access.lastSignedIn", {
                        when: formatDateTime(member.app_signed_in_at, display),
                      })}
                    </span>
                  )}
                </Row>
                {member.reader_pin && (
                  <Row label={t("readers.number")}>
                    {member.reader_pin}
                    <span className="block text-xs font-normal text-slate-500">
                      {t("readers.numberHelp")}
                    </span>
                  </Row>
                )}
              </dl>
              {member.notes && (
                <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-950">
                  {member.notes}
                </p>
              )}
            </Card>
          </div>
        )}
        {tab === "memberships" && (
          <Card>
            <MembershipsList member={member} />
          </Card>
        )}
        {tab === "training" &&
          (training.error ? (
            <Notice tone="error">{training.error}</Notice>
          ) : training.data ? (
            <TrainingTab
              memberId={member.id}
              homeBranchId={member.home_branch_id}
              branches={branches}
              packages={training.data}
              canSell={!member.is_archived && !erased}
              onChanged={reloadAll}
            />
          ) : (
            <ListSkeleton rows={2} />
          ))}
        {tab === "payments" && (
          <Card>
            <PaymentsTable payments={member.payments} />
          </Card>
        )}
        {tab === "visits" && (
          <Card className="max-w-md">
            <VisitsCalendar
              memberId={member.id}
              calendar={display === "ad" ? "ad" : "bs"}
            />
          </Card>
        )}
        {tab === "messages" && (
          <Card>
            <Messages memberId={member.id} />
          </Card>
        )}
        {tab === "history" && (
          <Card>
            <HistoryTab memberId={member.id} />
          </Card>
        )}
      </Tabs>

      {dialog === "pay" && (
        <CollectPayment
          open
          memberships={member.memberships}
          onClose={() => setDialog(null)}
          onDone={(payment) => {
            setDialog(null);
            toast.success(t("payment.recorded", { number: payment.receipt_no }));
            reload();
          }}
        />
      )}
      {dialog === "whatsapp" && (
        <WhatsAppDialog
          memberId={member.id}
          // Never in the app yet: the welcome, with its link.
          purpose={member.app_signed_in_at ? "reminder" : "welcome"}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "signIn" && (
        <SignInQr
          memberId={member.id}
          name={member.name}
          signedInAt={member.app_signed_in_at}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "sms" && (
        <SendSms
          memberId={member.id}
          onClose={() => setDialog(null)}
          onSent={() => {
            setDialog(null);
            toast.success(t("sms.queued"));
          }}
        />
      )}
      {dialog === "edit" && (
        <EditMember
          open
          member={member}
          branches={branches}
          onClose={() => setDialog(null)}
          onSaved={(saved) => {
            setDialog(null);
            setData(saved);
            toast.success(t("member.saved"));
          }}
        />
      )}
      {dialog === "erase" && (
        <EraseMember
          member={member}
          onClose={() => setDialog(null)}
          onErased={(gone) => {
            setDialog(null);
            setData(gone);
          }}
        />
      )}
    </div>
  );
}
