"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Form } from "@/components/Form";
import { Notice } from "@/components/Notice";
import { Card } from "@/components/ui/Card";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { Dialog } from "@/components/ui/Dialog";
import { Checkbox, MoneyInput, Select } from "@/components/ui/inputs";
import { Money } from "@/components/ui/Money";
import { AccessHoursEditor } from "@/components/settings/AccessHoursEditor";
import { describeHours, type AccessWindow } from "@/lib/accessHours";
import { plural, t, type MessageKey } from "@/i18n";
import {
  classesApi,
  branchesApi,
  errorMessage,
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
  if (plan.duration_months)
    return plural(plan.duration_months, "plans.months.one", "plans.months.other");
  return plural(plan.duration_days ?? 0, "plans.days.one", "plans.days.other");
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
      <ul className="divide-y divide-hairline">
        {branches?.map((b) => (
          <li key={b.id} className="flex items-center justify-between py-2 text-sm">
            <span className={b.is_active ? "" : "text-slate-500"}>{b.name}</span>
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
      <Form
        onSubmit={() =>
          run(async () => {
            await branchesApi.create({ name });
            setName("");
          })
        }
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
      </Form>
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
      <ul className="divide-y divide-hairline">
        {plans.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              onClick={() => setEditing(p)}
              className="flex w-full items-center justify-between py-2 text-left text-sm hover:bg-slate-50"
            >
              <span className={p.is_active ? "" : "text-slate-500"}>
                <span className="font-medium">{p.name}</span>
                <span className="text-slate-500"> · {duration(p)}</span>
                {p.visit_limit && (
                  <span className="text-slate-500">
                    {" "}
                    · {t("plans.visits", { count: p.visit_limit })}
                  </span>
                )}
                {p.seats > 1 && (
                  <span className="text-slate-500">
                    {" "}
                    · {t("plans.forPeople", { count: p.seats })}
                  </span>
                )}
                {p.access_hours && (
                  <span className="block text-xs text-slate-500">
                    {describeHours(p.access_hours)}
                  </span>
                )}
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
    visit_limit: plan?.visit_limit ? String(plan.visit_limit) : "",
    access_hours: (plan?.access_hours ?? []) as AccessWindow[],
    seats: plan?.seats ?? 1,
    classes: plan?.classes ?? "all",
    class_type_ids: plan?.class_type_ids ?? [],
  });
  // Classes it includes (§19.4): asked once the gym runs any.
  const classTypes = useLoad(() => classesApi.types(), []).data ?? [];
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
      // A visit pack is for one person (§19.1).
      visit_limit:
        form.visit_limit && form.seats === 1 ? Number(form.visit_limit) : null,
      access_hours: form.access_hours.length ? form.access_hours : null,
      seats: form.seats,
      classes: form.classes,
      class_type_ids: form.classes === "chosen" ? form.class_type_ids : null,
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
      <Form onSubmit={save} className="space-y-3">
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
        <Select
          label={t("plans.seats")}
          value={String(form.seats)}
          onChange={(seats) => setForm({ ...form, seats: Number(seats) })}
          options={[1, 2, 3, 4, 5, 6].map((n) => ({
            value: String(n),
            label: n === 1 ? t("plans.seats.one") : t("plans.seats.many", { count: n }),
          }))}
          help={t("plans.seatsHelp")}
        />
        {classTypes.length > 0 && (
          <div>
            <Select<"none" | "all" | "chosen">
              label={t("plans.classes")}
              value={form.classes}
              onChange={(classes) => setForm({ ...form, classes })}
              options={(["all", "chosen", "none"] as const).map((c) => ({
                value: c,
                label: t(`plans.classes.${c}`),
              }))}
              help={t("plans.classesHelp")}
            />
            {form.classes === "chosen" &&
              classTypes.map((k) => (
                <Checkbox
                  key={k.id}
                  label={k.name}
                  checked={form.class_type_ids.includes(k.id)}
                  onChange={(on) =>
                    setForm({
                      ...form,
                      class_type_ids: on
                        ? [...form.class_type_ids, k.id]
                        : form.class_type_ids.filter((id) => id !== k.id),
                    })
                  }
                />
              ))}
          </div>
        )}
        {form.seats === 1 && (
          <Field
            label={t("plans.visitLimit")}
            value={form.visit_limit}
            onChange={(visit_limit) => setForm({ ...form, visit_limit })}
            type="number"
            inputMode="numeric"
            help={t("plans.visitLimitHelp")}
            optional
            optionalLabel={t("common.optional")}
          />
        )}
        <div>
          <Checkbox
            label={t("plans.offPeak")}
            hint={t("plans.offPeakHelp")}
            checked={form.access_hours.length > 0}
            onChange={(on) =>
              setForm({
                ...form,
                access_hours: on
                  ? [{ days: [0, 1, 2, 3, 4, 5, 6], from: "06:00", to: "10:00" }]
                  : [],
              })
            }
          />
          {form.access_hours.length > 0 && (
            <div className="mt-2">
              <AccessHoursEditor
                value={form.access_hours}
                onChange={(access_hours) => setForm({ ...form, access_hours })}
              />
            </div>
          )}
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
      </Form>
    </Dialog>
  );
}

const ACCOUNT_KINDS: AccountKind[] = ["esewa", "khalti", "fonepay", "bank", "other"];

/** The wallets that can confirm members' app payments themselves (§20.2). */
const WALLETS: AccountKind[] = ["esewa", "khalti", "fonepay"];

export function PaymentMethodsSection() {
  const { data: methods, reload } = useLoad(() => paymentMethodsApi.list(true), []);
  const [adding, setAdding] = useState(false);
  const [keysFor, setKeysFor] = useState<PaymentMethodAccount | null>(null);
  const [error, setError] = useState<string | null>(null);
  const confirm = useConfirm();
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
            className={`flex gap-3 rounded-xl p-3 ring-1 ${m.is_active ? "ring-hairline" : "border border-dashed border-slate-300 opacity-60 ring-transparent"}`}
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
                {WALLETS.includes(m.kind) && (
                  <Button variant="ghost" onClick={() => setKeysFor(m)}>
                    {m.gateway
                      ? t("paymentMethods.gatewayChange")
                      : t("paymentMethods.gatewaySetUp")}
                  </Button>
                )}
                {m.gateway && (
                  <Button
                    variant="ghost"
                    onClick={async () => {
                      const wallet = t(`account.${m.kind}` as MessageKey);
                      const yes = await confirm({
                        title: t("paymentMethods.gatewayRemove"),
                        message: t("paymentMethods.gatewayRemoveConfirm", {
                          wallet,
                          label: m.label,
                        }),
                        confirmLabel: t("paymentMethods.gatewayRemove"),
                        danger: true,
                      });
                      if (yes) void run(() => paymentMethodsApi.removeGateway(m.id));
                    }}
                  >
                    {t("paymentMethods.gatewayRemove")}
                  </Button>
                )}
              </div>
              {m.gateway && <GatewayState method={m} />}
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
      {keysFor && (
        <GatewayDialog
          method={keysFor}
          onClose={() => setKeysFor(null)}
          onSaved={() => {
            setKeysFor(null);
            reload();
          }}
        />
      )}
    </Card>
  );
}

/** Whether the wallet confirms payments to this account, and its last word. */
function GatewayState({ method }: { method: PaymentMethodAccount }) {
  const gateway = method.gateway!;
  const wallet = t(`account.${method.kind}` as MessageKey);
  return (
    <div className="mt-2 space-y-1 rounded-lg bg-slate-50 p-2 text-xs">
      <p className="font-semibold text-emerald-800">
        {t("paymentMethods.gatewayOn", { wallet })}
      </p>
      {gateway.hint && (
        <p className="text-slate-600">
          {t("paymentMethods.gatewayHint", { hint: gateway.hint })}
        </p>
      )}
      {gateway.test && (
        <p className="text-amber-800">
          {t("paymentMethods.gatewayTestOn", { wallet })}
        </p>
      )}
      {gateway.error && (
        <p className="text-red-700">
          {t("paymentMethods.gatewayError", { wallet, error: gateway.error })}
        </p>
      )}
    </div>
  );
}

/** The keys from the gym's merchant account (§20.2). Never shown again. */
function GatewayDialog({
  method,
  onClose,
  onSaved,
}: {
  method: PaymentMethodAccount;
  onClose: () => void;
  onSaved: () => void;
}) {
  const wallet = t(`account.${method.kind}` as MessageKey);
  const [form, setForm] = useState({
    merchant: method.gateway?.merchant ?? "",
    secret_key: "",
    username: "",
    password: "",
    test: method.gateway?.test ?? false,
  });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const needsMerchant = method.kind !== "khalti";
  const needsLogin = method.kind === "fonepay";

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await paymentMethodsApi.setGateway(method.id, {
        merchant: needsMerchant ? form.merchant.trim() : null,
        secret_key: form.secret_key.trim(),
        username: needsLogin ? form.username.trim() : null,
        password: needsLogin ? form.password : null,
        test: form.test,
      });
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
      setSaving(false);
    }
  }

  return (
    <Dialog open onClose={onClose} title={t("paymentMethods.gatewayTitle", { wallet })}>
      <form onSubmit={(e) => void save(e)} className="space-y-3">
        <p className="text-sm text-slate-600">
          {t("paymentMethods.gatewayHelp", { wallet })}
        </p>
        {needsMerchant && (
          <Field
            label={
              method.kind === "esewa"
                ? t("paymentMethods.gatewayMerchantEsewa")
                : t("paymentMethods.gatewayMerchant")
            }
            value={form.merchant}
            onChange={(merchant) => setForm({ ...form, merchant })}
            autoComplete="off"
            required
          />
        )}
        <Field
          label={
            method.kind === "khalti"
              ? t("paymentMethods.gatewaySecretKhalti")
              : t("paymentMethods.gatewaySecret")
          }
          type="password"
          value={form.secret_key}
          onChange={(secret_key) => setForm({ ...form, secret_key })}
          autoComplete="off"
          required
        />
        {needsLogin && (
          <div className="grid grid-cols-2 gap-3">
            <Field
              label={t("paymentMethods.gatewayUsername")}
              value={form.username}
              onChange={(username) => setForm({ ...form, username })}
              autoComplete="off"
              required
            />
            <Field
              label={t("paymentMethods.gatewayPassword")}
              type="password"
              value={form.password}
              onChange={(password) => setForm({ ...form, password })}
              autoComplete="off"
              required
            />
          </div>
        )}
        <Checkbox
          label={t("paymentMethods.gatewayTest", { wallet })}
          hint={t("paymentMethods.gatewayTestHelp", { wallet })}
          checked={form.test}
          onChange={(test) => setForm({ ...form, test })}
        />
        <p className="text-xs text-slate-500">
          {t("paymentMethods.gatewayWhere", { wallet })}
        </p>
        <p className="text-xs text-slate-500">
          {t("paymentMethods.gatewayFees", { wallet })}
        </p>
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block disabled={saving}>
          {saving ? t("common.saving") : t("common.save")}
        </Button>
      </form>
    </Dialog>
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
      <Form
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
      </Form>
    </Dialog>
  );
}
