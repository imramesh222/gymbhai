"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Card, PageHeader } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { Select } from "@/components/ui/inputs";
import { Money } from "@/components/ui/Money";
import { t, type MessageKey } from "@/i18n";
import { adminApi, errorMessage, type AdminGym } from "@/lib/api";
import { formatAd, formatDateTime } from "@/lib/dates";
import { useLoad } from "@/lib/useLoad";

type Action = "grant" | "credits" | "suspend" | "password";

export default function AdminGymsPage() {
  const [q, setQ] = useState("");
  const gyms = useLoad(() => adminApi.gyms(q || undefined), [q]);
  const payments = useLoad(() => adminApi.payments(), []);
  const plans = useLoad(() => adminApi.plans(), []).data ?? [];
  const [open, setOpen] = useState<{ gym: AdminGym; action: Action } | null>(null);
  const [message, setMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);

  async function run(action: () => Promise<unknown>, done: MessageKey) {
    setMessage(null);
    try {
      await action();
      setMessage({ tone: "success", text: t(done) });
      gyms.reload();
      payments.reload();
      setOpen(null);
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader title={t("admin.gyms")} />
      {message && <Notice tone={message.tone}>{message.text}</Notice>}

      {payments.data && payments.data.length > 0 && (
        <Card
          title={t("admin.pendingPayments", { count: payments.data.length })}
          className="border-amber-300"
        >
          <ul className="divide-y divide-slate-100 text-sm">
            {payments.data.map((p) => (
              <li
                key={p.id}
                className="flex flex-wrap items-center justify-between gap-2 py-2"
              >
                <span>
                  <span className="font-semibold">{p.gym_name}</span> ·{" "}
                  {p.kind === "sms"
                    ? t("subscription.smsCredits", { count: p.sms_credits ?? 0 })
                    : `${p.plan_name} × ${p.months}`}{" "}
                  · <Money paisa={p.amount} /> · {p.transaction_ref}
                  <span className="block text-xs text-slate-500">
                    {formatDateTime(p.created_at, "ad")}
                  </span>
                </span>
                <span className="flex gap-2">
                  <Button
                    onClick={() => run(() => adminApi.approve(p.id), "admin.approved")}
                  >
                    {t("requests.approve")}
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      const reason = window.prompt(t("requests.reason"));
                      if (reason)
                        void run(() => adminApi.reject(p.id, reason), "admin.rejected");
                    }}
                  >
                    {t("requests.reject")}
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <input
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={t("admin.search")}
        aria-label={t("admin.search")}
        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5"
      />
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs text-slate-500 uppercase">
            <tr>
              <th className="px-3 py-2">{t("admin.gym")}</th>
              <th className="px-3 py-2">{t("admin.owner")}</th>
              <th className="px-3 py-2">{t("admin.plan")}</th>
              <th className="px-3 py-2">{t("admin.ends")}</th>
              <th className="px-3 py-2">{t("admin.members")}</th>
              <th className="px-3 py-2">{t("admin.sms")}</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {gyms.data?.map((g) => (
              <tr key={g.id} className={g.status === "suspended" ? "bg-red-50" : ""}>
                <td className="px-3 py-2">
                  <p className="font-medium">{g.name}</p>
                  <p className="text-xs text-slate-500">
                    /{g.slug}
                    {g.status === "suspended" && ` · ${t("admin.suspended")}`}
                  </p>
                </td>
                <td className="px-3 py-2">
                  {g.owner_name}
                  <p className="text-xs text-slate-500">
                    {g.owner_phone ?? g.owner_email}
                  </p>
                </td>
                <td className="px-3 py-2">{g.plan_name ?? "—"}</td>
                <td className="px-3 py-2">
                  {g.ends_on ? formatAd(g.ends_on) : "—"}
                  <p className="text-xs text-slate-500">
                    {t(`subscription.phase.${g.phase}` as MessageKey)}
                  </p>
                </td>
                <td className="px-3 py-2">{g.active_members}</td>
                <td className="px-3 py-2">{g.sms_balance}</td>
                <td className="px-3 py-2">
                  <Select<Action>
                    label={t("admin.actions")}
                    value=""
                    onChange={(action) => setOpen({ gym: g, action })}
                    options={[
                      { value: "grant", label: t("admin.grant") },
                      { value: "credits", label: t("admin.addCredits") },
                      {
                        value: "suspend",
                        label:
                          g.status === "suspended"
                            ? t("admin.unsuspend")
                            : t("admin.suspend"),
                      },
                      { value: "password", label: t("admin.resetOwner") },
                    ]}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {open && (
        <ActionDialog
          gym={open.gym}
          action={open.action}
          plans={plans.map((p) => ({ value: p.id, label: p.name }))}
          onClose={() => setOpen(null)}
          run={run}
        />
      )}
    </div>
  );
}

function ActionDialog({
  gym,
  action,
  plans,
  onClose,
  run,
}: {
  gym: AdminGym;
  action: Action;
  plans: { value: string; label: string }[];
  onClose: () => void;
  run: (action: () => Promise<unknown>, done: MessageKey) => Promise<void>;
}) {
  const [value, setValue] = useState(
    action === "grant" ? "1" : action === "credits" ? "500" : "",
  );
  const [planId, setPlanId] = useState(plans[0]?.value ?? "");
  const [reason, setReason] = useState("");
  const unsuspend = action === "suspend" && gym.status === "suspended";

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (action === "grant")
      void run(
        () =>
          adminApi.grant(gym.id, {
            platform_plan_id: planId || null,
            months: Number(value),
          }),
        "admin.granted",
      );
    else if (action === "credits")
      void run(
        () => adminApi.credits(gym.id, Number(value), reason),
        "admin.creditsAdded",
      );
    else if (action === "suspend")
      void run(
        () =>
          unsuspend ? adminApi.unsuspend(gym.id) : adminApi.suspend(gym.id, reason),
        unsuspend ? "admin.unsuspendedDone" : "admin.suspendedDone",
      );
    else void run(() => adminApi.ownerPassword(gym.id, value), "admin.passwordReset");
  }

  return (
    <Dialog open onClose={onClose} title={`${gym.name}`}>
      <form onSubmit={submit} className="space-y-3">
        {action === "grant" && (
          <>
            <Select
              label={t("admin.plan")}
              value={planId}
              onChange={setPlanId}
              options={plans}
            />
            <Field
              label={t("subscription.months")}
              value={value}
              onChange={setValue}
              type="number"
              required
            />
          </>
        )}
        {action === "credits" && (
          <>
            <Field
              label={t("subscription.credits")}
              value={value}
              onChange={setValue}
              type="number"
              required
            />
            <Field
              label={t("membership.reason")}
              value={reason}
              onChange={setReason}
              required
            />
          </>
        )}
        {action === "suspend" && !unsuspend && (
          <>
            <Notice tone="warning">{t("admin.suspendHelp")}</Notice>
            <Field
              label={t("membership.reason")}
              value={reason}
              onChange={setReason}
              required
            />
          </>
        )}
        {action === "password" && (
          <Field
            label={t("team.newPassword")}
            value={value}
            onChange={setValue}
            type="password"
            autoComplete="new-password"
            required
          />
        )}
        <Button
          type="submit"
          block
          variant={action === "suspend" && !unsuspend ? "danger" : "primary"}
        >
          {t("common.confirm")}
        </Button>
      </form>
    </Dialog>
  );
}
