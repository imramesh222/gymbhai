"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useRef, useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { AccessCard } from "@/components/member/AccessCard";
import { CollectPayment } from "@/components/member/CollectPayment";
import { EditMember } from "@/components/member/EditMember";
import { PaymentsTable } from "@/components/member/PaymentsTable";
import { SendSms } from "@/components/member/SendSms";
import { Avatar } from "@/components/ui/Avatar";
import { Card, PageHeader, Row } from "@/components/ui/Card";
import { Money } from "@/components/ui/Money";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { t } from "@/i18n";
import { branchesApi, errorMessage, membersApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useGymCalendar } from "@/lib/gym";
import { shrinkImage } from "@/lib/image";
import { useLoad } from "@/lib/useLoad";

export default function MemberPage() {
  const { id } = useParams<{ id: string }>();
  const receipt = useSearchParams().get("receipt");
  const { can } = useAuth();
  const { date } = useGymCalendar();
  const {
    data: member,
    error,
    reload,
    setData,
  } = useLoad(() => membersApi.get(id), [id]);
  const branches = useLoad(() => branchesApi.list(), []).data ?? [];
  const [dialog, setDialog] = useState<"pay" | "edit" | "sms" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const photoInput = useRef<HTMLInputElement>(null);

  if (error) return <Notice tone="error">{error}</Notice>;
  if (!member) return <p className="text-sm text-slate-500">{t("common.loading")}</p>;

  const branchName = branches.find((b) => b.id === member.home_branch_id)?.name;

  async function run(action: () => Promise<unknown>) {
    setActionError(null);
    try {
      await action();
      reload();
    } catch (err) {
      setActionError(errorMessage(err));
    }
  }

  async function changePhoto(file: File | undefined) {
    if (!file) return;
    await run(async () =>
      setData(await membersApi.uploadPhoto(member!.id, await shrinkImage(file))),
    );
  }

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
      {notice && <Notice tone="success">{notice}</Notice>}
      {actionError && <Notice tone="error">{actionError}</Notice>}

      <PageHeader
        title={
          <span className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => can("members.edit") && photoInput.current?.click()}
              aria-label={t("member.changePhoto")}
              title={t("member.changePhoto")}
            >
              <Avatar name={member.name} url={member.photo_url} size="size-14" />
            </button>
            <span className="min-w-0">
              <span className="block truncate">{member.name}</span>
              <span className="block text-sm font-normal text-slate-500">
                {member.member_code} · {member.phone}
              </span>
            </span>
          </span>
        }
        actions={
          <>
            {can("memberships.sell") && !member.is_archived && (
              <Link href={`/staff/members/${member.id}/renew`}>
                <Button>
                  {member.status === "none" ? t("member.sell") : t("member.renew")}
                </Button>
              </Link>
            )}
            {can("payments.collect") && member.dues > 0 && (
              <Button variant="secondary" onClick={() => setDialog("pay")}>
                {t("payment.collect")}
              </Button>
            )}
            {can("messages.sms") && (
              <Button variant="secondary" onClick={() => setDialog("sms")}>
                {t("sms.send")}
              </Button>
            )}
            {can("members.edit") && (
              <Button variant="secondary" onClick={() => setDialog("edit")}>
                {t("common.edit")}
              </Button>
            )}
          </>
        }
      />
      <input
        ref={photoInput}
        type="file"
        accept="image/*"
        capture="user"
        className="hidden"
        onChange={(e) => void changePhoto(e.target.files?.[0])}
      />

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="md:col-span-1">
          <div className="flex items-center justify-between">
            <StatusBadge status={member.is_archived ? "cancelled" : member.status} />
            {member.is_archived && (
              <span className="text-xs text-slate-500">{t("member.archived")}</span>
            )}
          </div>
          {(member.status === "active" || member.status === "frozen") && (
            <p className="mt-3 text-4xl font-bold tracking-tight text-slate-900">
              {member.days_left}
              <span className="ml-1 text-base font-medium text-slate-600">
                {t("member.daysLeftLabel")}
              </span>
            </p>
          )}
          <dl className="mt-4 divide-y divide-hairline">
            {member.current && (
              <Row label={t("member.plan")}>{member.current.plan_name}</Row>
            )}
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
          </dl>
          {member.notes && (
            <p className="mt-2 rounded bg-slate-50 p-2 text-sm text-slate-700">
              {member.notes}
            </p>
          )}
          {can("members.archive") && (
            <div className="mt-3 text-right">
              <Button
                variant="ghost"
                onClick={() =>
                  run(async () => {
                    if (member.is_archived) await membersApi.unarchive(member.id);
                    else if (window.confirm(t("member.archiveConfirm")))
                      await membersApi.archive(member.id);
                  })
                }
              >
                {member.is_archived ? t("member.unarchive") : t("member.archive")}
              </Button>
            </div>
          )}
        </Card>
      </div>

      <AccessCard member={member} onChanged={reload} />

      <Card title={t("member.memberships")}>
        {member.memberships.length === 0 && (
          <p className="text-sm text-slate-500">{t("member.noMemberships")}</p>
        )}
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
      </Card>

      <Card title={t("member.payments")}>
        <PaymentsTable payments={member.payments} />
      </Card>

      {dialog === "pay" && (
        <CollectPayment
          open
          memberships={member.memberships}
          onClose={() => setDialog(null)}
          onDone={(payment) => {
            setDialog(null);
            setNotice(t("payment.recorded", { number: payment.receipt_no }));
            reload();
          }}
        />
      )}
      {dialog === "sms" && (
        <SendSms
          memberId={member.id}
          onClose={() => setDialog(null)}
          onSent={() => {
            setDialog(null);
            setNotice(t("sms.queued"));
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
          }}
        />
      )}
    </div>
  );
}
