"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { History } from "@/components/member/History";
import { PaymentsTable } from "@/components/member/PaymentsTable";
import {
  PaymentFields,
  toPaymentInput,
  type PaymentDraft,
} from "@/components/money/PaymentFields";
import { Card, PageHeader, Row } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { DateInput, MoneyInput, Select, TextArea } from "@/components/ui/inputs";
import { Money } from "@/components/ui/Money";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { t } from "@/i18n";
import {
  branchesApi,
  errorMessage,
  membersApi,
  membershipsApi,
  paymentsApi,
  plansApi,
  type Membership,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { todayInNepal } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";

type DialogName = "edit" | "extend" | "freeze" | "cancel" | "void" | null;

export default function MembershipPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { can } = useAuth();
  const { date, display } = useGymCalendar();
  const [tab, setTab] = useState<"details" | "history">("details");
  const [dialog, setDialog] = useState<DialogName>(null);
  const [voidId, setVoidId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const {
    data,
    error: loadError,
    reload,
  } = useLoad(async () => {
    const membership = await membershipsApi.get(id);
    const [member, history, plans, branches] = await Promise.all([
      membersApi.get(membership.member_id),
      membershipsApi.history(id),
      plansApi.list(true),
      branchesApi.list(),
    ]);
    return { membership, member, history, plans, branches };
  }, [id]);

  if (loadError) return <Notice tone="error">{loadError}</Notice>;
  if (!data) return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
  const { membership: m, member, history, plans, branches } = data;
  const payments = member.payments.filter((p) => p.membership_id === m.id);
  const live = m.status !== "cancelled";

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      setDialog(null);
      reload();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const today = todayInNepal();
  const openFreeze = m.freezes.find((f) => f.to_date >= today);

  return (
    <div className="space-y-4">
      <PageHeader
        title={m.plan_name}
        subtitle={
          <Link
            href={`/staff/members/${member.id}`}
            className="text-brand-700 hover:underline"
          >
            {member.name} · {member.member_code}
          </Link>
        }
        actions={
          live && (
            <>
              {can("memberships.edit") && (
                <Button variant="secondary" onClick={() => setDialog("edit")}>
                  {t("common.edit")}
                </Button>
              )}
              {can("memberships.extend") && (
                <Button variant="secondary" onClick={() => setDialog("extend")}>
                  {t("membership.extend")}
                </Button>
              )}
              {can("memberships.freeze") && (
                <Button variant="secondary" onClick={() => setDialog("freeze")}>
                  {t("membership.freeze")}
                </Button>
              )}
              {can("memberships.cancel") && (
                <Button variant="danger" onClick={() => setDialog("cancel")}>
                  {t("membership.cancel")}
                </Button>
              )}
            </>
          )
        }
      />
      {error && !dialog && <Notice tone="error">{error}</Notice>}

      <div className="flex gap-1 border-b border-hairline">
        {(["details", "history"] as const).map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setTab(name)}
            className={`-mb-px border-b-2 px-3.5 py-2.5 text-sm font-semibold transition ${
              tab === name
                ? "border-brand-600 text-brand-700"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {t(name === "details" ? "membership.details" : "membership.history")}
          </button>
        ))}
      </div>

      {tab === "history" ? (
        <Card>
          <History entries={history} />
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <div className="mb-2 flex items-center gap-2">
              <StatusBadge status={m.status} />
              {(m.status === "active" || m.status === "frozen") && (
                <span className="text-sm text-slate-600">
                  {t("members.daysLeft", { count: m.days_left })}
                </span>
              )}
            </div>
            <dl>
              <Row label={t("sale.start")}>{date(m.start_date)}</Row>
              <Row label={t("sale.end")}>{date(m.end_date)}</Row>
              <Row label={t("sale.branch")}>
                {branches.find((b) => b.id === m.branch_id)?.name ?? "—"}
              </Row>
              <Row label={t("sale.price")}>
                <Money paisa={m.price} />
              </Row>
              <Row label={t("sale.discount")}>
                <Money paisa={m.discount} />
              </Row>
              <Row label={t("sale.admissionFee")}>
                <Money paisa={m.admission_fee} />
              </Row>
              <Row label={t("sale.total")}>
                <Money paisa={m.total} />
              </Row>
              <Row label={t("membership.paid")}>
                <Money paisa={m.paid} />
              </Row>
              <Row label={t("member.dues")}>
                <Money paisa={m.dues} className={m.dues > 0 ? "text-amber-700" : ""} />
              </Row>
            </dl>
            {m.cancel_reason && (
              <p className="mt-2 text-sm text-slate-600">
                {t("membership.cancelledBecause", { reason: m.cancel_reason })}
              </p>
            )}
            {m.freezes.length > 0 && (
              <div className="mt-3">
                <h3 className="text-sm font-semibold">{t("membership.freezes")}</h3>
                <ul className="mt-1 space-y-1 text-sm">
                  {m.freezes.map((f) => (
                    <li key={f.id} className="flex items-center justify-between gap-2">
                      <span>
                        {date(f.from_date)} → {date(f.to_date)}
                        {f.reason && (
                          <span className="text-slate-500"> · {f.reason}</span>
                        )}
                      </span>
                      {f === openFreeze && can("memberships.freeze") && (
                        <Button
                          variant="ghost"
                          onClick={() =>
                            run(() => membershipsApi.endFreeze(m.id, f.id))
                          }
                        >
                          {t("membership.endFreeze")}
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {can("memberships.delete") && (
              <div className="mt-4 text-right">
                <Button
                  variant="ghost"
                  onClick={() =>
                    window.confirm(t("membership.deleteConfirm")) &&
                    run(async () => {
                      await membershipsApi.remove(m.id);
                      router.replace(`/staff/members/${member.id}`);
                    })
                  }
                >
                  {t("membership.delete")}
                </Button>
              </div>
            )}
          </Card>
          <Card title={t("member.payments")}>
            <PaymentsTable payments={payments} />
            {can("payments.void") && payments.some((p) => !p.voided_at) && (
              <div className="mt-3">
                <Select
                  label={t("payment.voidOne")}
                  value={voidId ?? ""}
                  onChange={(value) => {
                    setVoidId(value);
                    setDialog("void");
                  }}
                  options={payments
                    .filter((p) => !p.voided_at)
                    .map((p) => ({ value: p.id, label: `#${p.receipt_no}` }))}
                />
              </div>
            )}
          </Card>
        </div>
      )}

      {dialog === "edit" && (
        <EditDialog
          membership={m}
          plans={plans}
          branches={branches}
          display={display}
          error={error}
          onClose={() => setDialog(null)}
          onSave={(body) => run(() => membershipsApi.update(m.id, body))}
        />
      )}
      {dialog === "extend" && (
        <ReasonDialog
          title={t("membership.extend")}
          error={error}
          withDays
          onClose={() => setDialog(null)}
          onSave={(reason, days) =>
            run(() => membershipsApi.extend(m.id, days, reason))
          }
        />
      )}
      {dialog === "freeze" && (
        <FreezeDialog
          display={display}
          error={error}
          onClose={() => setDialog(null)}
          onSave={(from, to, reason) =>
            run(() => membershipsApi.freeze(m.id, from, to, reason))
          }
        />
      )}
      {dialog === "cancel" && (
        <CancelDialog
          paid={m.paid}
          canRefund={can("payments.refund")}
          error={error}
          onClose={() => setDialog(null)}
          onSave={(reason, refund) =>
            run(() => membershipsApi.cancel(m.id, reason, refund))
          }
        />
      )}
      {dialog === "void" && voidId && (
        <ReasonDialog
          title={t("payment.void")}
          error={error}
          onClose={() => {
            setDialog(null);
            setVoidId(null);
          }}
          onSave={(reason) => run(() => paymentsApi.void(voidId, reason))}
        />
      )}
    </div>
  );
}

function EditDialog({
  membership,
  plans,
  branches,
  display,
  error,
  onClose,
  onSave,
}: {
  membership: Membership;
  plans: { id: string; name: string }[];
  branches: { id: string; name: string }[];
  display: "ad" | "bs" | "both";
  error: string | null;
  onClose: () => void;
  onSave: (body: Record<string, unknown>) => void;
}) {
  const [form, setForm] = useState({
    plan_id: membership.plan_id ?? "",
    branch_id: membership.branch_id,
    start_date: membership.start_date,
    end_date: membership.end_date,
    price: membership.price as number | null,
    discount: membership.discount as number | null,
    admission_fee: membership.admission_fee as number | null,
    reason: "",
  });
  return (
    <Dialog open onClose={onClose} title={t("membership.edit")}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          // Only what changed, so a plan change can still recalculate the rest.
          const body: Record<string, unknown> = { reason: form.reason || null };
          for (const key of [
            "plan_id",
            "branch_id",
            "start_date",
            "end_date",
            "price",
            "discount",
            "admission_fee",
          ] as const) {
            if (form[key] !== (membership as unknown as Record<string, unknown>)[key]) {
              body[key] = form[key];
            }
          }
          onSave(body);
        }}
        className="space-y-3"
      >
        <Select
          label={t("sale.plan")}
          value={form.plan_id}
          onChange={(plan_id) => setForm({ ...form, plan_id })}
          options={plans.map((p) => ({ value: p.id, label: p.name }))}
        />
        <p className="text-xs text-slate-500">{t("membership.planChangeHelp")}</p>
        {branches.length > 1 && (
          <Select
            label={t("sale.branch")}
            value={form.branch_id}
            onChange={(branch_id) => setForm({ ...form, branch_id })}
            options={branches.map((b) => ({ value: b.id, label: b.name }))}
          />
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <DateInput
            label={t("sale.start")}
            value={form.start_date}
            onChange={(start_date) => setForm({ ...form, start_date })}
            display={display}
          />
          <DateInput
            label={t("sale.end")}
            value={form.end_date}
            onChange={(end_date) => setForm({ ...form, end_date })}
            display={display}
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <MoneyInput
            label={t("sale.price")}
            value={form.price}
            onChange={(price) => setForm({ ...form, price })}
          />
          <MoneyInput
            label={t("sale.discount")}
            value={form.discount}
            onChange={(discount) => setForm({ ...form, discount })}
          />
          <MoneyInput
            label={t("sale.admissionFee")}
            value={form.admission_fee}
            onChange={(admission_fee) => setForm({ ...form, admission_fee })}
          />
        </div>
        <TextArea
          label={t("membership.reason")}
          value={form.reason}
          onChange={(reason) => setForm({ ...form, reason })}
        />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block>
          {t("common.save")}
        </Button>
      </form>
    </Dialog>
  );
}

function ReasonDialog({
  title,
  withDays,
  error,
  onClose,
  onSave,
}: {
  title: string;
  withDays?: boolean;
  error: string | null;
  onClose: () => void;
  onSave: (reason: string, days: number) => void;
}) {
  const [reason, setReason] = useState("");
  const [days, setDays] = useState("7");
  return (
    <Dialog open onClose={onClose} title={title}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSave(reason, Number(days));
        }}
        className="space-y-3"
      >
        {withDays && (
          <Field
            label={t("membership.days")}
            value={days}
            onChange={setDays}
            type="number"
            inputMode="numeric"
            required
          />
        )}
        <TextArea
          label={t("membership.reason")}
          value={reason}
          onChange={setReason}
          required
        />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block>
          {t("common.confirm")}
        </Button>
      </form>
    </Dialog>
  );
}

function FreezeDialog({
  display,
  error,
  onClose,
  onSave,
}: {
  display: "ad" | "bs" | "both";
  error: string | null;
  onClose: () => void;
  onSave: (from: string, to: string, reason: string) => void;
}) {
  const [from, setFrom] = useState(todayInNepal());
  const [to, setTo] = useState(todayInNepal());
  const [reason, setReason] = useState("");
  return (
    <Dialog open onClose={onClose} title={t("membership.freeze")}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSave(from, to, reason);
        }}
        className="space-y-3"
      >
        <p className="text-sm text-slate-600">{t("membership.freezeHelp")}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <DateInput
            label={t("membership.freezeFrom")}
            value={from}
            onChange={setFrom}
            display={display}
            required
          />
          <DateInput
            label={t("membership.freezeTo")}
            value={to}
            onChange={setTo}
            display={display}
            required
          />
        </div>
        <TextArea label={t("membership.reason")} value={reason} onChange={setReason} />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block>
          {t("membership.freeze")}
        </Button>
      </form>
    </Dialog>
  );
}

function CancelDialog({
  paid,
  canRefund,
  error,
  onClose,
  onSave,
}: {
  paid: number;
  canRefund: boolean;
  error: string | null;
  onClose: () => void;
  onSave: (reason: string, refund: ReturnType<typeof toPaymentInput>) => void;
}) {
  const [reason, setReason] = useState("");
  const [refund, setRefund] = useState<PaymentDraft>({
    amount: null,
    method: "cash",
    transactionRef: "",
  });
  return (
    <Dialog open onClose={onClose} title={t("membership.cancel")}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSave(reason, canRefund ? toPaymentInput(refund) : null);
        }}
        className="space-y-3"
      >
        <TextArea
          label={t("membership.reason")}
          value={reason}
          onChange={setReason}
          required
        />
        {canRefund && paid > 0 && (
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
        <Button type="submit" variant="danger" block>
          {t("membership.cancel")}
        </Button>
      </form>
    </Dialog>
  );
}
