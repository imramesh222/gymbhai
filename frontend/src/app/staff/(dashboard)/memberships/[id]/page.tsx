"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Form } from "@/components/Form";
import { Notice } from "@/components/Notice";
import { History } from "@/components/member/History";
import { MemberPicker, type Picked } from "@/components/member/MemberPicker";
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
  type Plan,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { todayInNepal } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { useToast } from "@/components/ui/Toast";
import { PageSkeleton } from "@/components/ui/Skeleton";

type DialogName = "edit" | "extend" | "freeze" | "cancel" | "void" | "add" | null;

export default function MembershipPage() {
  const confirm = useConfirm();
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();
  const { can } = useAuth();
  const { date, display } = useGymCalendar();
  const [tab, setTab] = useState<"details" | "history">("details");
  // The member's More menu opens this page with ?do=freeze.
  const wanted = useSearchParams().get("do");
  const [dialog, setDialog] = useState<DialogName>(
    wanted === "freeze" ? "freeze" : null,
  );
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
  if (!data) return <PageSkeleton label={t("common.loading")} />;
  const { membership: m, member, history, plans, branches } = data;
  const payments = member.payments.filter((p) => p.membership_id === m.id);
  const live = m.status !== "cancelled";
  // A family or couple plan (§19.1): the money is on the payer's membership.
  const group = m.group;
  const payer = group?.people.find((p) => p.member_id === group.payer_member_id);
  const paysHere = !group || group.payer_member_id === m.member_id;
  const stillOn = group?.people.filter((p) => !p.cancelled) ?? [];

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      setDialog(null);
      toast.success(t("common.saved"));
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
                  {paysHere ? t("membership.cancel") : t("membership.removeFromPlan")}
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
              {paysHere ? (
                <>
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
                    <Money
                      paisa={m.dues}
                      className={m.dues > 0 ? "text-amber-700" : ""}
                    />
                  </Row>
                </>
              ) : (
                payer && (
                  <Row label={t("membership.paidBy")}>
                    <Link
                      href={`/staff/memberships/${payer.membership_id}`}
                      className="text-brand-700 hover:underline"
                    >
                      {payer.name}
                    </Link>
                  </Row>
                )
              )}
            </dl>
            {!paysHere && payer && (
              <p className="mt-2 text-xs text-slate-500">
                {t("membership.paidByHelp", { name: payer.name })}
              </p>
            )}
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
                  onClick={async () =>
                    (await confirm({
                      title: t("membership.delete"),
                      message: t("membership.deleteConfirm"),
                      confirmLabel: t("membership.delete"),
                      danger: true,
                    })) &&
                    run(async () => {
                      await membershipsApi.remove(m.id);
                      toast.success(t("membership.deleted"));
                      router.replace(`/staff/members/${member.id}`);
                    })
                  }
                >
                  {t("membership.delete")}
                </Button>
              </div>
            )}
          </Card>
          {group && (
            <Card
              title={t("membership.onPlan")}
              actions={
                <span className="text-xs text-slate-500">
                  {t("membership.onPlanCount", {
                    count: stillOn.length,
                    seats: group.seats,
                  })}
                </span>
              }
            >
              <ul className="divide-y divide-hairline">
                {group.people.map((p) => (
                  <li key={p.membership_id}>
                    <Link
                      href={`/staff/memberships/${p.membership_id}`}
                      className="flex items-center justify-between gap-2 py-2 text-sm hover:bg-slate-50"
                    >
                      <span className={p.cancelled ? "text-slate-400" : "font-medium"}>
                        {p.name}
                        <span className="text-slate-500"> · {p.member_code}</span>
                      </span>
                      <span className="text-xs text-slate-500">
                        {p.member_id === group.payer_member_id && t("membership.pays")}
                        {p.cancelled && t("membership.removed")}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
              {live &&
                can("memberships.sell") &&
                stillOn.length < group.seats &&
                payer &&
                !payer.cancelled && (
                  <Button
                    variant="secondary"
                    size="sm"
                    className="mt-3"
                    onClick={() => setDialog("add")}
                  >
                    {t("membership.addPerson")}
                  </Button>
                )}
            </Card>
          )}
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
          // A family or couple plan changes only to one for as many people.
          plans={plans.filter((p) => p.seats === (group?.seats ?? 1))}
          moneyOnPayer={!paysHere}
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
          title={paysHere ? t("membership.cancel") : t("membership.removeFromPlan")}
          everyone={
            paysHere && stillOn.length > 1 ? stillOn.map((p) => p.name) : undefined
          }
          paid={m.paid}
          canRefund={can("payments.refund")}
          error={error}
          onClose={() => setDialog(null)}
          onSave={(reason, refund) =>
            run(() => membershipsApi.cancel(m.id, reason, refund))
          }
        />
      )}
      {dialog === "add" && group && (
        <AddPersonDialog
          exclude={stillOn.map((p) => p.member_id)}
          display={display}
          error={error}
          onClose={() => setDialog(null)}
          onSave={(person, start) =>
            run(async () => {
              await membershipsApi.addToGroup(group.id, person.id, start);
              toast.success(t("membership.added"));
            })
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
  moneyOnPayer,
  branches,
  display,
  error,
  onClose,
  onSave,
}: {
  membership: Membership;
  plans: Plan[];
  /** Someone else pays for this plan: its plan and price are on theirs. */
  moneyOnPayer: boolean;
  branches: { id: string; name: string }[];
  display: "ad" | "bs" | "both";
  error: string | null;
  onClose: () => void;
  onSave: (body: Record<string, unknown>) => Promise<unknown>;
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
      <Form
        onSubmit={() => {
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
          return onSave(body);
        }}
        className="space-y-3"
      >
        {!moneyOnPayer && (
          <>
            <Select
              label={t("sale.plan")}
              value={form.plan_id}
              onChange={(plan_id) => setForm({ ...form, plan_id })}
              options={plans.map((p) => ({ value: p.id, label: p.name }))}
            />
            <p className="text-xs text-slate-500">{t("membership.planChangeHelp")}</p>
          </>
        )}
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
        {!moneyOnPayer && (
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
        )}
        <TextArea
          label={t("membership.reason")}
          value={form.reason}
          onChange={(reason) => setForm({ ...form, reason })}
        />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block>
          {t("common.save")}
        </Button>
      </Form>
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
  onSave: (reason: string, days: number) => Promise<unknown>;
}) {
  const [reason, setReason] = useState("");
  const [days, setDays] = useState("7");
  return (
    <Dialog open onClose={onClose} title={title}>
      <Form onSubmit={() => onSave(reason, Number(days))} className="space-y-3">
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
      </Form>
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
  onSave: (from: string, to: string, reason: string) => Promise<unknown>;
}) {
  const [from, setFrom] = useState(todayInNepal());
  const [to, setTo] = useState(todayInNepal());
  const [reason, setReason] = useState("");
  return (
    <Dialog open onClose={onClose} title={t("membership.freeze")}>
      <Form onSubmit={() => onSave(from, to, reason)} className="space-y-3">
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
      </Form>
    </Dialog>
  );
}

function CancelDialog({
  title,
  everyone,
  paid,
  canRefund,
  error,
  onClose,
  onSave,
}: {
  title: string;
  /** Cancelling the payer's cancels the plan for everyone on it (§19.1). */
  everyone?: string[];
  paid: number;
  canRefund: boolean;
  error: string | null;
  onClose: () => void;
  onSave: (
    reason: string,
    refund: ReturnType<typeof toPaymentInput>,
  ) => Promise<unknown>;
}) {
  const [reason, setReason] = useState("");
  const [refund, setRefund] = useState<PaymentDraft>({
    amount: null,
    method: "cash",
    transactionRef: "",
  });
  return (
    <Dialog open onClose={onClose} title={title}>
      <Form
        onSubmit={() => onSave(reason, canRefund ? toPaymentInput(refund) : null)}
        className="space-y-3"
      >
        {everyone && (
          <Notice tone="warning">
            {t("membership.cancelEveryone", { names: everyone.join(", ") })}
          </Notice>
        )}
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
          {title}
        </Button>
      </Form>
    </Dialog>
  );
}

function AddPersonDialog({
  exclude,
  display,
  error,
  onClose,
  onSave,
}: {
  exclude: string[];
  display: "ad" | "bs" | "both";
  error: string | null;
  onClose: () => void;
  onSave: (person: Picked, start: string | null) => void;
}) {
  const [person, setPerson] = useState<Picked | null>(null);
  const [start, setStart] = useState("");
  return (
    <Dialog open onClose={onClose} title={t("membership.addPerson")}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (person) onSave(person, start || null);
        }}
        className="space-y-3"
      >
        <MemberPicker
          label={t("sale.withFind")}
          value={person}
          onChange={setPerson}
          exclude={exclude}
        />
        <DateInput
          label={t("membership.addPersonStart")}
          value={start}
          onChange={setStart}
          display={display}
        />
        <p className="text-xs text-slate-500">{t("membership.addPersonHelp")}</p>
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block disabled={!person}>
          {t("membership.addPerson")}
        </Button>
      </form>
    </Dialog>
  );
}
