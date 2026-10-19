"use client";

import { CalendarCheck, Pencil, Plus, Wallet, XCircle } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { PaymentsTable } from "@/components/member/PaymentsTable";
import {
  PaymentFields,
  toPaymentInput,
  type PaymentDraft,
} from "@/components/money/PaymentFields";
import { EmptyState } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { DateInput, Select, TextArea } from "@/components/ui/inputs";
import { Menu } from "@/components/ui/Menu";
import { Money } from "@/components/ui/Money";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/Toast";
import { t } from "@/i18n";
import {
  errorMessage,
  ptApi,
  type Branch,
  type Payment,
  type PtPackageDetail,
  type PtSession,
  type Trainer,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useGymCalendar } from "@/lib/gym";
import { useIdempotencyKey } from "@/lib/idempotency";
import { formatRs } from "@/lib/money";
import { mayCorrect, mayRecord, sessionsLine } from "@/lib/training";
import { useLoad } from "@/lib/useLoad";

import { RecordSession } from "./RecordSession";
import { SellTraining } from "./SellTraining";

type Open =
  | { name: "sell" }
  | { name: "record" | "collect" | "change" | "cancel"; pkg: PtPackageDetail }
  | { name: "void"; pkg: PtPackageDetail; session: PtSession }
  | null;

/**
 * The member profile's Personal training tab (PLAN.md §18.3): every package,
 * with its sessions, its money and what can be done with it. Its own dues:
 * a membership's never count them.
 */
export function TrainingTab({
  memberId,
  homeBranchId,
  branches,
  packages,
  canSell,
  onChanged,
}: {
  memberId: string;
  homeBranchId: string;
  branches: Branch[];
  packages: PtPackageDetail[];
  /** Selling more: not for an archived or erased member. */
  canSell: boolean;
  onChanged: () => void;
}) {
  const { can, me } = useAuth();
  const toast = useToast();
  const [open, setOpen] = useState<Open>(null);

  function done(message: string) {
    setOpen(null);
    toast.success(message);
    onChanged();
  }

  return (
    <div className="space-y-4">
      {canSell && can("pt.sell") && (
        <div className="flex justify-end">
          <Button onClick={() => setOpen({ name: "sell" })}>
            <Plus className="size-4" aria-hidden />
            {t("pt.sell")}
          </Button>
        </div>
      )}
      {packages.length === 0 && <EmptyState title={t("pt.none")} />}
      {packages.map((pkg) => (
        <PackageCard
          key={pkg.id}
          pkg={pkg}
          records={mayRecord(pkg, me?.staff.id, can)}
          corrects={mayCorrect(pkg, me?.staff.id, can)}
          onOpen={(name) => setOpen({ name, pkg })}
          onVoid={(session) => setOpen({ name: "void", pkg, session })}
        />
      ))}

      {open?.name === "sell" && (
        <SellTraining
          memberId={memberId}
          homeBranchId={homeBranchId}
          branches={branches}
          onClose={() => setOpen(null)}
          onSold={() => done(t("pt.sold"))}
        />
      )}
      {open?.name === "record" && (
        <RecordSession
          pkg={open.pkg}
          onClose={() => setOpen(null)}
          onRecorded={() => done(t("pt.recorded"))}
        />
      )}
      {open?.name === "collect" && (
        <CollectTraining
          pkg={open.pkg}
          onClose={() => setOpen(null)}
          onDone={(payment) =>
            done(t("payment.recorded", { number: payment.receipt_no }))
          }
        />
      )}
      {open?.name === "change" && (
        <ChangePackage
          pkg={open.pkg}
          onClose={() => setOpen(null)}
          onDone={() => done(t("common.saved"))}
        />
      )}
      {open?.name === "cancel" && (
        <CancelPackage
          pkg={open.pkg}
          canRefund={can("payments.refund")}
          onClose={() => setOpen(null)}
          onDone={() => done(t("pt.cancelled"))}
        />
      )}
      {open?.name === "void" && (
        <VoidSession
          session={open.session}
          onClose={() => setOpen(null)}
          onDone={() => done(t("pt.voided"))}
        />
      )}
    </div>
  );
}

function PackageCard({
  pkg,
  records,
  corrects,
  onOpen,
  onVoid,
}: {
  pkg: PtPackageDetail;
  records: boolean;
  corrects: boolean;
  onOpen: (name: "record" | "collect" | "change" | "cancel") => void;
  onVoid: (session: PtSession) => void;
}) {
  const { can } = useAuth();
  const { date } = useGymCalendar();
  const live = pkg.status !== "cancelled";
  return (
    <section
      className="rounded-2xl bg-surface p-4 shadow-card ring-1 ring-hairline"
      aria-label={pkg.plan_name}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-semibold text-slate-900">{pkg.plan_name}</h3>
          <p className="text-sm text-slate-600">
            {pkg.trainer_name} · {date(pkg.start_date)} → {date(pkg.end_date)}
          </p>
          <p className="mt-1 text-sm font-medium text-slate-800">{sessionsLine(pkg)}</p>
          <p className="text-xs text-slate-500">
            {pkg.last_session_on
              ? t("pt.lastSession", { date: date(pkg.last_session_on) })
              : t("pt.noSessionYet")}
          </p>
          {pkg.cancel_reason && (
            <p className="mt-1 text-sm text-slate-600">
              {t("pt.cancelledBecause", { reason: pkg.cancel_reason })}
            </p>
          )}
        </div>
        <div className="shrink-0 text-right">
          <StatusBadge status={pkg.status} />
          <p className="mt-1 text-xs text-slate-500">
            <Money paisa={pkg.paid} /> / <Money paisa={pkg.total} />
          </p>
          {pkg.dues > 0 && (
            <p className="text-xs font-medium text-amber-700">
              {t("members.owes")} <Money paisa={pkg.dues} />
            </p>
          )}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {records && (
          <Button size="sm" onClick={() => onOpen("record")}>
            <CalendarCheck className="size-3.5" aria-hidden />
            {t("pt.record")}
          </Button>
        )}
        {live && pkg.dues > 0 && can("payments.collect") && (
          <Button size="sm" variant="secondary" onClick={() => onOpen("collect")}>
            <Wallet className="size-3.5" aria-hidden />
            {t("payment.collect")}
          </Button>
        )}
        {live && can("pt.sell") && (
          <Menu
            compact
            label={t("pt.moreFor", { plan: pkg.plan_name })}
            items={[
              {
                label: t("pt.change"),
                icon: Pencil,
                onSelect: () => onOpen("change"),
              },
              {
                label: t("pt.cancel"),
                icon: XCircle,
                danger: true,
                onSelect: () => onOpen("cancel"),
              },
            ]}
          />
        )}
      </div>

      {pkg.session_log.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm font-medium text-slate-700">
            {t("pt.sessions")} ({pkg.sessions_used})
          </summary>
          <ul className="mt-2 divide-y divide-hairline">
            {pkg.session_log.map((session) => (
              <li
                key={session.id}
                className="flex items-start justify-between gap-3 py-2 text-sm"
              >
                <div
                  className={`min-w-0 ${session.voided_at ? "text-slate-500 line-through" : ""}`}
                >
                  <p className="font-medium">
                    {date(session.trained_on)}
                    {session.trainer_name && ` · ${session.trainer_name}`}
                  </p>
                  {session.note && <p className="text-slate-600">{session.note}</p>}
                  {session.recorded_by_name &&
                    session.recorded_by_name !== session.trainer_name && (
                      <p className="text-xs text-slate-500">
                        {t("pt.recordedBy", { name: session.recorded_by_name })}
                      </p>
                    )}
                  {session.voided_at && (
                    <p className="text-xs text-red-700 no-underline">
                      {t("payment.voidedBecause", {
                        reason: session.void_reason ?? "",
                      })}
                    </p>
                  )}
                </div>
                {corrects && !session.voided_at && (
                  <Button size="sm" variant="ghost" onClick={() => onVoid(session)}>
                    {t("pt.voidSession")}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
      {pkg.payments.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-sm font-medium text-slate-700">
            {t("member.payments")} ({pkg.payments.length})
          </summary>
          <div className="mt-2">
            <PaymentsTable payments={pkg.payments} showPurpose={false} />
          </div>
        </details>
      )}
    </section>
  );
}

/** Money towards it: an ordinary payment, with its own receipt. */
function CollectTraining({
  pkg,
  onClose,
  onDone,
}: {
  pkg: PtPackageDetail;
  onClose: () => void;
  onDone: (payment: Payment) => void;
}) {
  const [draft, setDraft] = useState<PaymentDraft>({
    amount: pkg.dues,
    method: "cash",
    transactionRef: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const saving = useIdempotencyKey();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const payment = toPaymentInput(draft);
    if (!payment) return;
    setPending(true);
    setError(null);
    try {
      const saved = await ptApi.collect(
        pkg.id,
        payment,
        saving.keyFor({ pkg: pkg.id, payment }),
      );
      saving.succeeded();
      onDone(saved);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open onClose={onClose} title={t("payment.collect")}>
      <form onSubmit={(e) => void submit(e)} className="space-y-4">
        <p className="text-sm text-slate-600">
          {pkg.plan_name} — {t("payment.owes", { amount: formatRs(pkg.dues) })}
        </p>
        <PaymentFields value={draft} onChange={setDraft} owed={pkg.dues} />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block disabled={pending || !draft.amount}>
          {pending ? t("common.saving") : t("payment.record")}
        </Button>
      </form>
    </Dialog>
  );
}

function ChangePackage({
  pkg,
  onClose,
  onDone,
}: {
  pkg: PtPackageDetail;
  onClose: () => void;
  onDone: () => void;
}) {
  const { display } = useGymCalendar();
  const trainers = useLoad(() => ptApi.trainers(), []);
  const [trainerId, setTrainerId] = useState(pkg.trainer_id);
  const [startDate, setStartDate] = useState(pkg.start_date);
  const [endDate, setEndDate] = useState(pkg.end_date);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  // Someone no longer training stays choosable on the packages they had.
  const choices: Trainer[] = [
    ...(trainers.data ?? []),
    ...(trainers.data?.some((tr) => tr.id === pkg.trainer_id)
      ? []
      : [{ id: pkg.trainer_id, name: pkg.trainer_name ?? "—" }]),
  ];

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      await ptApi.update(pkg.id, {
        ...(trainerId !== pkg.trainer_id ? { trainer_id: trainerId } : {}),
        ...(startDate !== pkg.start_date ? { start_date: startDate } : {}),
        ...(endDate !== pkg.end_date ? { end_date: endDate } : {}),
        reason: reason.trim() || null,
      });
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open onClose={onClose} title={t("pt.change")}>
      <form onSubmit={(e) => void submit(e)} className="space-y-3">
        <Select
          label={t("pt.trainer")}
          value={trainerId}
          onChange={setTrainerId}
          options={choices.map((tr) => ({ value: tr.id, label: tr.name }))}
        />
        <div className="grid gap-3 sm:grid-cols-2">
          <DateInput
            label={t("sale.start")}
            value={startDate}
            onChange={setStartDate}
            display={display}
            required
          />
          <DateInput
            label={t("sale.end")}
            value={endDate}
            onChange={setEndDate}
            display={display}
            required
          />
        </div>
        <TextArea label={t("membership.reason")} value={reason} onChange={setReason} />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block disabled={pending}>
          {pending ? t("common.saving") : t("common.save")}
        </Button>
      </form>
    </Dialog>
  );
}

function CancelPackage({
  pkg,
  canRefund,
  onClose,
  onDone,
}: {
  pkg: PtPackageDetail;
  canRefund: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const [refund, setRefund] = useState<PaymentDraft>({
    amount: null,
    method: "cash",
    transactionRef: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      await ptApi.cancel(pkg.id, reason, canRefund ? toPaymentInput(refund) : null);
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open onClose={onClose} title={t("pt.cancel")}>
      <form onSubmit={(e) => void submit(e)} className="space-y-3">
        <TextArea
          label={t("membership.reason")}
          value={reason}
          onChange={setReason}
          required
        />
        {canRefund && pkg.paid > 0 && (
          <div>
            <h3 className="mb-2 text-sm font-semibold">
              {t("membership.refundOptional")}
            </h3>
            <PaymentFields
              value={refund}
              onChange={setRefund}
              amountLabel={t("membership.refundAmount")}
            />
          </div>
        )}
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" variant="danger" block disabled={pending}>
          {t("pt.cancel")}
        </Button>
      </form>
    </Dialog>
  );
}

function VoidSession({
  session,
  onClose,
  onDone,
}: {
  session: PtSession;
  onClose: () => void;
  onDone: () => void;
}) {
  const { date } = useGymCalendar();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      await ptApi.voidSession(session.id, reason);
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open onClose={onClose} title={t("pt.voidSession")}>
      <form onSubmit={(e) => void submit(e)} className="space-y-3">
        <p className="text-sm text-slate-600">
          {date(session.trained_on)}
          {session.trainer_name && ` · ${session.trainer_name}`}
        </p>
        <TextArea
          label={t("membership.reason")}
          value={reason}
          onChange={setReason}
          required
        />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" variant="danger" block disabled={pending}>
          {t("pt.voidSession")}
        </Button>
      </form>
    </Dialog>
  );
}
