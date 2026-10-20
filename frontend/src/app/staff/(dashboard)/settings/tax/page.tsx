"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Card } from "@/components/ui/Card";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { Checkbox, DateInput } from "@/components/ui/inputs";
import { t } from "@/i18n";
import { errorMessage, taxApi, type TaxSettings } from "@/lib/api";
import { todayInNepal } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";

/**
 * Settings → Tax (PLAN.md §20.4): VAT invoices for a VAT-registered gym, and
 * reporting each to IRD's CBMS. Off on a server until GymBhai is certified.
 */
export default function TaxSettingsPage() {
  const { display } = useGymCalendar();
  const { data, setData, error } = useLoad(() => taxApi.settings(), []);
  const confirm = useConfirm();
  const [form, setForm] = useState<{
    vat_registered: boolean;
    pan: string;
    starts_on: string;
  } | null>(null);
  const [login, setLogin] = useState({ username: "", password: "" });
  const [message, setMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);

  if (error) return <Notice tone="error">{error}</Notice>;
  if (!data) return <PageSkeleton label={t("common.loading")} />;

  async function run(action: () => Promise<TaxSettings>) {
    setMessage(null);
    try {
      setData(await action());
      setForm(null);
      setMessage({ tone: "success", text: t("common.saved") });
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  if (!data.available)
    return (
      <Card title={t("tax.title")}>
        <Notice>{t("tax.unavailable")}</Notice>
      </Card>
    );

  const shown = form ?? {
    vat_registered: data.vat_registered,
    pan: data.pan ?? "",
    starts_on: data.starts_on ?? todayInNepal(),
  };
  const counts = data.cbms_counts;

  return (
    <>
      <Card title={t("tax.title")}>
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            void run(() =>
              taxApi.update({
                vat_registered: shown.vat_registered,
                pan: shown.pan.trim() || null,
                starts_on: shown.vat_registered ? shown.starts_on : null,
              }),
            );
          }}
        >
          <p className="text-sm text-slate-600">{t("tax.help")}</p>
          <Checkbox
            label={t("tax.registered")}
            checked={shown.vat_registered}
            onChange={(vat_registered) => setForm({ ...shown, vat_registered })}
          />
          {shown.vat_registered && (
            <div className="grid gap-3 sm:grid-cols-2">
              <Field
                label={t("tax.pan")}
                help={t("tax.panHelp")}
                value={shown.pan}
                onChange={(pan) =>
                  setForm({ ...shown, pan: pan.replace(/\D/g, "").slice(0, 9) })
                }
                inputMode="numeric"
                required
              />
              <DateInput
                label={t("tax.startsOn")}
                value={shown.starts_on}
                onChange={(starts_on) => setForm({ ...shown, starts_on })}
                display={display}
                required
              />
              <p className="text-xs text-slate-500 sm:col-span-2">
                {t("tax.startsOnHelp")}
              </p>
            </div>
          )}
          {data.invoices > 0 && (
            <p className="text-sm text-slate-600">
              {t("tax.issued", { count: data.invoices })}
            </p>
          )}
          <Button type="submit">{t("common.save")}</Button>
        </form>
      </Card>

      {data.vat_registered && (
        <Card title={t("tax.cbms")}>
          <div className="space-y-3">
            <p className="text-sm text-slate-600">{t("tax.cbmsHelp")}</p>
            {data.cbms_enabled ? (
              <>
                <p className="text-sm font-semibold text-emerald-800">
                  {t("tax.cbmsOn", { username: data.cbms_username ?? "" })}
                </p>
                <p className="text-sm text-slate-600">
                  {t("tax.cbmsCounts", {
                    sent: counts.sent ?? 0,
                    waiting: counts.waiting ?? 0,
                    refused: counts.refused ?? 0,
                  })}
                </p>
                {data.cbms_error && (
                  <Notice tone="error">
                    {t("tax.cbmsError", { error: data.cbms_error })}
                  </Notice>
                )}
                <Button
                  variant="ghost"
                  onClick={async () => {
                    const yes = await confirm({
                      title: t("tax.cbmsOff"),
                      message: t("tax.cbmsHelp"),
                      confirmLabel: t("tax.cbmsOff"),
                      danger: true,
                    });
                    if (yes) void run(() => taxApi.removeCbms());
                  }}
                >
                  {t("tax.cbmsOff")}
                </Button>
              </>
            ) : null}
            <form
              className="grid gap-3 sm:grid-cols-2"
              onSubmit={(event) => {
                event.preventDefault();
                void run(() => taxApi.setCbms(login)).then(() =>
                  setLogin({ username: "", password: "" }),
                );
              }}
            >
              <Field
                label={t("tax.cbmsUsername")}
                value={login.username}
                onChange={(username) => setLogin({ ...login, username })}
                autoComplete="off"
                required
              />
              <Field
                label={t("tax.cbmsPassword")}
                type="password"
                value={login.password}
                onChange={(password) => setLogin({ ...login, password })}
                autoComplete="off"
                required
              />
              <div className="sm:col-span-2">
                <Button type="submit" variant="secondary">
                  {t("common.save")}
                </Button>
              </div>
            </form>
          </div>
        </Card>
      )}
      {message && <Notice tone={message.tone}>{message.text}</Notice>}
    </>
  );
}
