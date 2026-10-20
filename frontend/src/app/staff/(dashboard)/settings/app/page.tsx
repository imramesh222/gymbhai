"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Card } from "@/components/ui/Card";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { t, type MessageKey } from "@/i18n";
import { errorMessage, gymAppApi, type BrandedApp } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatRs } from "@/lib/money";
import { useLoad } from "@/lib/useLoad";

/**
 * Settings → Your own app (PLAN.md §20.3): the gym's own app in the Play
 * Store and App Store, asked for here and built by us.
 */
export default function OwnAppPage() {
  const { me } = useAuth();
  const { data, setData, error } = useLoad(() => gymAppApi.get(), []);
  const confirm = useConfirm();
  const [form, setForm] = useState<{ app_name: string; color: string } | null>(null);
  const [message, setMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);
  const [saving, setSaving] = useState(false);
  const iconInput = useRef<HTMLInputElement>(null);

  if (error) return <Notice tone="error">{error}</Notice>;
  if (!data) return <PageSkeleton label={t("common.loading")} />;

  const editable =
    data.status === null || data.status === "asked" || data.status === "stopped";
  const shown = form ?? {
    app_name: data.app_name ?? me?.gym?.name?.slice(0, 30) ?? "",
    color: data.color ?? me?.gym?.brand_color ?? "#1d5fd1",
  };

  async function run(action: () => Promise<BrandedApp>) {
    setSaving(true);
    setMessage(null);
    try {
      setData(await action());
      setForm(null);
      setMessage({ tone: "success", text: t("ownApp.saved") });
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title={t("ownApp.title")}>
      <div className="space-y-4">
        <p className="text-sm text-slate-600">{t("ownApp.help")}</p>
        {!data.offered && data.status === null ? (
          <Notice>{t("ownApp.notOffered")}</Notice>
        ) : (
          <>
            {data.setup_price !== null && data.monthly_price !== null && (
              <p className="text-sm font-semibold text-slate-800">
                {t("ownApp.price", {
                  setup: formatRs(data.setup_price),
                  monthly: formatRs(data.monthly_price),
                })}
              </p>
            )}
            <p className="text-sm text-slate-600">{t("ownApp.accounts")}</p>

            {data.status && data.status !== "stopped" && (
              <Notice tone={data.status === "live" ? "success" : "info"}>
                {t(`ownApp.status.${data.status}` as MessageKey)}
              </Notice>
            )}
            {data.status && data.status !== "stopped" && (
              <p className="text-sm text-slate-600">
                {data.setup_paid ? (
                  t("ownApp.setupPaid")
                ) : (
                  <Link
                    href="/staff/subscription"
                    className="font-semibold text-brand-700"
                  >
                    {t("ownApp.payIt")}
                  </Link>
                )}
              </p>
            )}

            {(data.play_url || data.app_store_url) && (
              <div className="space-y-1 text-sm">
                <p className="font-semibold">{t("ownApp.inStores")}</p>
                {data.play_url && (
                  <a
                    href={data.play_url}
                    className="block text-brand-700"
                    target="_blank"
                    rel="noreferrer"
                  >
                    {t("ownApp.playStore")}
                  </a>
                )}
                {data.app_store_url && (
                  <a
                    href={data.app_store_url}
                    className="block text-brand-700"
                    target="_blank"
                    rel="noreferrer"
                  >
                    {t("ownApp.appStore")}
                  </a>
                )}
              </div>
            )}

            {editable ? (
              <form
                className="space-y-3"
                onSubmit={(event) => {
                  event.preventDefault();
                  void run(() => gymAppApi.ask(shown));
                }}
              >
                <Field
                  label={t("ownApp.name")}
                  help={t("ownApp.nameHelp")}
                  value={shown.app_name}
                  onChange={(app_name) =>
                    setForm({ ...shown, app_name: app_name.slice(0, 30) })
                  }
                  required
                />
                <label className="block text-sm">
                  <span className="font-medium">{t("ownApp.color")}</span>
                  <input
                    type="color"
                    value={shown.color}
                    onChange={(e) => setForm({ ...shown, color: e.target.value })}
                    className="mt-1 block h-10 w-20 rounded"
                  />
                </label>
                <Button type="submit" disabled={saving}>
                  {data.status === "asked" ? t("ownApp.save") : t("ownApp.ask")}
                </Button>
              </form>
            ) : (
              <p className="text-sm text-slate-600">{t("ownApp.started")}</p>
            )}

            {data.status && data.status !== "stopped" && (
              <div className="flex items-center gap-3">
                {data.icon_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={data.icon_url}
                    alt={t("ownApp.icon")}
                    className="size-20 rounded-2xl ring-1 ring-hairline"
                  />
                ) : (
                  <span className="flex size-20 items-center justify-center rounded-2xl bg-slate-100 text-center text-xs text-slate-500">
                    {t("ownApp.noIcon")}
                  </span>
                )}
                <div className="space-y-1">
                  <p className="text-xs text-slate-500">{t("ownApp.iconHelp")}</p>
                  {editable && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => iconInput.current?.click()}
                    >
                      {t("ownApp.uploadIcon")}
                    </Button>
                  )}
                </div>
                <input
                  ref={iconInput}
                  type="file"
                  accept="image/png,image/jpeg"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    e.target.value = "";
                    // Sent as it is: the server checks it's square and large.
                    if (file) void run(() => gymAppApi.uploadIcon(file));
                  }}
                />
              </div>
            )}

            {data.status === "asked" && (
              <Button
                variant="ghost"
                onClick={async () => {
                  const yes = await confirm({
                    title: t("ownApp.withdraw"),
                    message: t("ownApp.withdrawConfirm"),
                    confirmLabel: t("ownApp.withdraw"),
                    danger: true,
                  });
                  if (yes) void run(() => gymAppApi.withdraw());
                }}
              >
                {t("ownApp.withdraw")}
              </Button>
            )}
          </>
        )}
        {message && <Notice tone={message.tone}>{message.text}</Notice>}
      </div>
    </Card>
  );
}
