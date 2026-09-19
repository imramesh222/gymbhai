"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Card } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { Checkbox, MoneyInput, Select, TextArea } from "@/components/ui/inputs";
import { Money } from "@/components/ui/Money";
import { t, type MessageKey } from "@/i18n";
import {
  branchesApi,
  errorMessage,
  membershipsApi,
  paymentMethodsApi,
  plansApi,
  type AccountKind,
  type Branch,
  type PaymentMethodAccount,
  type Plan,
} from "@/lib/api";
import { shrinkImage } from "@/lib/image";
import { useLoad } from "@/lib/useLoad";

function duration(plan: Pick<Plan, "duration_months" | "duration_days">): string {
  if (plan.duration_months) return t("plans.months", { count: plan.duration_months });
  return t("plans.days", { count: plan.duration_days ?? 0 });
}

export function BranchesSection() {
  const { data: branches, reload } = useLoad(() => branchesApi.list(), []);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      reload();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Card title={t("settings.branches")}>
      <ul className="divide-y divide-slate-100">
        {branches?.map((b) => (
          <li key={b.id} className="flex items-center justify-between py-2 text-sm">
            <span className={b.is_active ? "" : "text-slate-400"}>{b.name}</span>
            <Button
              variant="ghost"
              onClick={() =>
                run(() => branchesApi.update(b.id, { is_active: !b.is_active }))
              }
            >
              {b.is_active ? t("settings.close") : t("settings.reopen")}
            </Button>
          </li>
        ))}
      </ul>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            await branchesApi.create({ name });
            setName("");
          });
        }}
        className="mt-3 flex items-end gap-2"
      >
        <div className="flex-1">
          <Field
            label={t("settings.newBranch")}
            value={name}
            onChange={setName}
            required
          />
        </div>
        <Button type="submit">{t("common.add")}</Button>
      </form>
      {error && (
        <div className="mt-2">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
    </Card>
  );
}

export function PlansSection() {
  const { data, reload } = useLoad(
    () => Promise.all([plansApi.list(true), branchesApi.list()]),
    [],
  );
  const [editing, setEditing] = useState<Plan | "new" | null>(null);
  const [plans, branches] = data ?? [[], []];
  return (
    <Card
      title={t("settings.plans")}
      actions={<Button onClick={() => setEditing("new")}>{t("plans.add")}</Button>}
    >
      <p className="mb-2 text-sm text-slate-600">{t("plans.help")}</p>
      <ul className="divide-y divide-slate-100">
        {plans.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              onClick={() => setEditing(p)}
              className="flex w-full items-center justify-between py-2 text-left text-sm hover:bg-slate-50"
            >
              <span className={p.is_active ? "" : "text-slate-400"}>
                <span className="font-medium">{p.name}</span>
                <span className="text-slate-500"> · {duration(p)}</span>
                {!p.is_active && <span> · {t("plans.hidden")}</span>}
              </span>
              <span className="text-right">
                {p.price === null ? (
                  <span className="font-medium text-amber-700">
                    {t("plans.setPrice")}
                  </span>
                ) : (
                  <Money paisa={p.price} className="font-semibold" />
                )}
                {p.admission_fee > 0 && (
                  <span className="block text-xs text-slate-500">
                    + <Money paisa={p.admission_fee} /> {t("plans.admission")}
                  </span>
                )}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {editing && (
        <PlanDialog
          plan={editing === "new" ? null : editing}
          branches={branches}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
    </Card>
  );
}

function PlanDialog({
  plan,
  branches,
  onClose,
  onSaved,
}: {
  plan: Plan | null;
  branches: Branch[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    name: plan?.name ?? "",
    unit: (plan?.duration_days ? "days" : "months") as "months" | "days",
    length: String(plan?.duration_months ?? plan?.duration_days ?? 1),
    price: plan?.price ?? null,
    admission_fee: plan?.admission_fee ?? 0,
    all_branches: plan?.all_branches ?? true,
    branch_ids: plan?.branch_ids ?? [],
    is_active: plan?.is_active ?? true,
  });
  const [error, setError] = useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const length = Number(form.length);
    const body = {
      name: form.name,
      duration_months: form.unit === "months" ? length : null,
      duration_days: form.unit === "days" ? length : null,
      price: form.price,
      admission_fee: form.admission_fee ?? 0,
      all_branches: form.all_branches,
      branch_ids: form.all_branches ? [] : form.branch_ids,
      ...(plan ? { is_active: form.is_active } : {}),
    };
    try {
      if (plan) await plansApi.update(plan.id, body);
      else await plansApi.create(body);
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Dialog open onClose={onClose} title={plan ? t("plans.edit") : t("plans.add")}>
      <form onSubmit={(e) => void save(e)} className="space-y-3">
        <Field
          label={t("plans.name")}
          value={form.name}
          onChange={(name) => setForm({ ...form, name })}
          required
        />
        <div className="grid grid-cols-2 gap-3">
          <Field
            label={t("plans.length")}
            value={form.length}
            onChange={(length) => setForm({ ...form, length })}
            type="number"
            inputMode="numeric"
            required
          />
          <Select<"months" | "days">
            label={t("plans.unit")}
            value={form.unit}
            onChange={(unit) => setForm({ ...form, unit })}
            options={[
              { value: "months", label: t("plans.unit.months") },
              { value: "days", label: t("plans.unit.days") },
            ]}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <MoneyInput
            label={t("sale.price")}
            value={form.price}
            onChange={(price) => setForm({ ...form, price })}
          />
          <MoneyInput
            label={t("sale.admissionFee")}
            value={form.admission_fee}
            onChange={(admission_fee) =>
              setForm({ ...form, admission_fee: admission_fee ?? 0 })
            }
          />
        </div>
        {branches.length > 1 && (
          <div>
            <Checkbox
              label={t("plans.allBranches")}
              checked={form.all_branches}
              onChange={(all_branches) => setForm({ ...form, all_branches })}
            />
            {!form.all_branches &&
              branches.map((b) => (
                <Checkbox
                  key={b.id}
                  label={b.name}
                  checked={form.branch_ids.includes(b.id)}
                  onChange={(on) =>
                    setForm({
                      ...form,
                      branch_ids: on
                        ? [...form.branch_ids, b.id]
                        : form.branch_ids.filter((id) => id !== b.id),
                    })
                  }
                />
              ))}
          </div>
        )}
        {plan && (
          <Checkbox
            label={t("plans.offered")}
            checked={form.is_active}
            onChange={(is_active) => setForm({ ...form, is_active })}
            hint={t("plans.offeredHelp")}
          />
        )}
        <p className="text-xs text-slate-500">{t("plans.changeHelp")}</p>
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block>
          {t("common.save")}
        </Button>
      </form>
    </Dialog>
  );
}

const ACCOUNT_KINDS: AccountKind[] = ["esewa", "khalti", "fonepay", "bank", "other"];

export function PaymentMethodsSection() {
  const { data: methods, reload } = useLoad(() => paymentMethodsApi.list(true), []);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const qrFor = useRef<string | null>(null);
  const qrInput = useRef<HTMLInputElement>(null);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      reload();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Card
      title={t("settings.paymentMethods")}
      actions={<Button onClick={() => setAdding(true)}>{t("common.add")}</Button>}
    >
      <p className="mb-2 text-sm text-slate-600">{t("paymentMethods.help")}</p>
      <ul className="grid gap-3 sm:grid-cols-2">
        {methods?.map((m) => (
          <li
            key={m.id}
            className={`flex gap-3 rounded-lg border p-3 ${m.is_active ? "border-slate-200" : "border-dashed border-slate-300 opacity-60"}`}
          >
            {m.qr_image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={m.qr_image_url}
                alt=""
                className="size-20 rounded object-contain"
              />
            ) : (
              <span className="flex size-20 items-center justify-center rounded bg-slate-100 text-center text-xs text-slate-500">
                {t("paymentMethods.noQr")}
              </span>
            )}
            <div className="min-w-0 flex-1 text-sm">
              <p className="font-semibold">{m.label}</p>
              <p className="text-slate-600">{m.account_name}</p>
              <p className="text-slate-600">{m.account_number}</p>
              <div className="mt-1 flex flex-wrap gap-1">
                <Button
                  variant="ghost"
                  onClick={() => {
                    qrFor.current = m.id;
                    qrInput.current?.click();
                  }}
                >
                  {t("paymentMethods.uploadQr")}
                </Button>
                <Button
                  variant="ghost"
                  onClick={() =>
                    run(() =>
                      paymentMethodsApi.update(m.id, { is_active: !m.is_active }),
                    )
                  }
                >
                  {m.is_active ? t("paymentMethods.hide") : t("paymentMethods.show")}
                </Button>
              </div>
            </div>
          </li>
        ))}
      </ul>
      <input
        ref={qrInput}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          const id = qrFor.current;
          e.target.value = "";
          // QR codes must stay sharp: keep them large.
          if (file && id)
            void run(async () =>
              paymentMethodsApi.uploadQr(id, await shrinkImage(file, 1600, 0.95)),
            );
        }}
      />
      {error && (
        <div className="mt-2">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
      {adding && (
        <AddMethodDialog
          onClose={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            reload();
          }}
        />
      )}
    </Card>
  );
}

function AddMethodDialog({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<Partial<PaymentMethodAccount>>({
    kind: "esewa",
    label: "eSewa",
  });
  const [error, setError] = useState<string | null>(null);
  return (
    <Dialog open onClose={onClose} title={t("paymentMethods.add")}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await paymentMethodsApi.create(form);
            onSaved();
          } catch (err) {
            setError(errorMessage(err));
          }
        }}
        className="space-y-3"
      >
        <Select<AccountKind>
          label={t("paymentMethods.kind")}
          value={form.kind ?? "esewa"}
          onChange={(kind) =>
            setForm({ ...form, kind, label: t(`account.${kind}` as MessageKey) })
          }
          options={ACCOUNT_KINDS.map((k) => ({
            value: k,
            label: t(`account.${k}` as MessageKey),
          }))}
        />
        <Field
          label={t("paymentMethods.label")}
          value={form.label ?? ""}
          onChange={(label) => setForm({ ...form, label })}
          required
        />
        <Field
          label={t("paymentMethods.accountName")}
          value={form.account_name ?? ""}
          onChange={(account_name) => setForm({ ...form, account_name })}
        />
        <Field
          label={t("paymentMethods.accountNumber")}
          value={form.account_number ?? ""}
          onChange={(account_number) => setForm({ ...form, account_number })}
        />
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block>
          {t("common.save")}
        </Button>
      </form>
    </Dialog>
  );
}

export function ExtendEveryoneSection() {
  const { data: branches } = useLoad(() => branchesApi.list(), []);
  const [days, setDays] = useState("7");
  const [reason, setReason] = useState("");
  const [branchId, setBranchId] = useState("all");
  const [message, setMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!window.confirm(t("extendAll.confirm", { days }))) return;
    try {
      const result = await membershipsApi.extendAll(
        Number(days),
        reason,
        branchId === "all" ? null : branchId,
      );
      setMessage({
        tone: "success",
        text: t("extendAll.done", { count: result.extended }),
      });
      setReason("");
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  return (
    <Card title={t("extendAll.title")}>
      <p className="mb-3 text-sm text-slate-600">{t("extendAll.help")}</p>
      <form onSubmit={(e) => void submit(e)} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field
            label={t("membership.days")}
            value={days}
            onChange={setDays}
            type="number"
            inputMode="numeric"
            required
          />
          {branches && branches.length > 1 && (
            <Select
              label={t("sale.branch")}
              value={branchId}
              onChange={setBranchId}
              options={[
                { value: "all", label: t("extendAll.allBranches") },
                ...branches.map((b) => ({ value: b.id, label: b.name })),
              ]}
            />
          )}
        </div>
        <TextArea
          label={t("membership.reason")}
          value={reason}
          onChange={setReason}
          required
        />
        {message && <Notice tone={message.tone}>{message.text}</Notice>}
        <Button type="submit">{t("extendAll.submit")}</Button>
      </form>
    </Card>
  );
}
