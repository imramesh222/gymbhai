"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Card, EmptyState, PageHeader } from "@/components/ui/Card";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { Select } from "@/components/ui/inputs";
import { t, type MessageKey } from "@/i18n";
import {
  adminApi,
  errorMessage,
  type AdminBrandedApp,
  type BrandedAppStatus,
} from "@/lib/api";
import { formatDate } from "@/lib/dates";
import { useLoad } from "@/lib/useLoad";

const STATUSES: BrandedAppStatus[] = [
  "asked",
  "building",
  "in_review",
  "live",
  "stopped",
];

/** Gyms' own apps in the stores (PLAN.md §20.3, docs/BRANDED_APPS.md). */
export default function AdminAppsPage() {
  const { data, reload, error } = useLoad(() => adminApi.apps(), []);
  return (
    <div className="space-y-4">
      <PageHeader title={t("admin.apps")} subtitle={t("admin.appsHelp")} />
      {error && <Notice tone="error">{error}</Notice>}
      {!data ? (
        <PageSkeleton label={t("common.loading")} />
      ) : data.length === 0 ? (
        <EmptyState title={t("admin.appsNone")} />
      ) : (
        data.map((app) => <AppCard key={app.id} app={app} onSaved={reload} />)
      )}
    </div>
  );
}

function AppCard({ app, onSaved }: { app: AdminBrandedApp; onSaved: () => void }) {
  const [form, setForm] = useState({
    status: app.status,
    android_package: app.android_package,
    ios_bundle_id: app.ios_bundle_id,
    expo_project_id: app.expo_project_id ?? "",
    play_url: app.play_url ?? "",
    app_store_url: app.app_store_url ?? "",
    notes: app.notes ?? "",
  });
  const [message, setMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);
  const built = app.building_at !== null;

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setMessage(null);
    try {
      await adminApi.updateApp(app.id, {
        status: form.status,
        ...(built
          ? {}
          : {
              android_package: form.android_package,
              ios_bundle_id: form.ios_bundle_id,
            }),
        expo_project_id: form.expo_project_id.trim() || null,
        play_url: form.play_url.trim() || null,
        app_store_url: form.app_store_url.trim() || null,
        notes: form.notes.trim() || null,
      });
      setMessage({ tone: "success", text: t("common.saved") });
      onSaved();
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  async function download() {
    try {
      const build = await adminApi.appBuild(app.id);
      const blob = new Blob([JSON.stringify(build, null, 2)], {
        type: "application/json",
      });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `${app.gym_slug}-build.json`;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  return (
    <Card title={`${app.app_name} · ${app.gym_name}`}>
      <form onSubmit={(e) => void save(e)} className="space-y-3">
        <div className="flex items-center gap-3 text-sm">
          {app.icon_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={app.icon_url}
              alt=""
              className="size-14 rounded-xl ring-1 ring-hairline"
            />
          ) : (
            <span
              className="size-14 rounded-xl ring-1 ring-hairline"
              style={{ background: app.color }}
            />
          )}
          <div>
            <p className="font-medium">/{app.gym_slug}</p>
            <p className="text-slate-600">
              {formatDate(app.asked_at.slice(0, 10), "ad")} ·{" "}
              {app.setup_paid_at
                ? t("admin.app.setupPaid")
                : t("admin.app.setupUnpaid")}
            </p>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Select<BrandedAppStatus>
            label={t("admin.app.status")}
            value={form.status}
            onChange={(status) => setForm({ ...form, status })}
            options={STATUSES.map((s) => ({
              value: s,
              label: t(`ownApp.status.${s}` as MessageKey),
            }))}
          />
          <Field
            label={t("admin.app.expo")}
            value={form.expo_project_id}
            onChange={(expo_project_id) => setForm({ ...form, expo_project_id })}
          />
          {built ? (
            // The stores fix them once it's built.
            <p className="text-sm sm:col-span-2">
              <span className="font-medium">{t("admin.app.package")}:</span>{" "}
              {app.android_package} ·{" "}
              <span className="font-medium">{t("admin.app.bundle")}:</span>{" "}
              {app.ios_bundle_id}
            </p>
          ) : (
            <>
              <Field
                label={t("admin.app.package")}
                value={form.android_package}
                onChange={(android_package) => setForm({ ...form, android_package })}
              />
              <Field
                label={t("admin.app.bundle")}
                value={form.ios_bundle_id}
                onChange={(ios_bundle_id) => setForm({ ...form, ios_bundle_id })}
              />
            </>
          )}
          <Field
            label={t("admin.app.play")}
            value={form.play_url}
            onChange={(play_url) => setForm({ ...form, play_url })}
            type="url"
          />
          <Field
            label={t("admin.app.appStore")}
            value={form.app_store_url}
            onChange={(app_store_url) => setForm({ ...form, app_store_url })}
            type="url"
          />
        </div>
        <Field
          label={t("admin.app.notes")}
          value={form.notes}
          onChange={(notes) => setForm({ ...form, notes })}
        />
        {message && <Notice tone={message.tone}>{message.text}</Notice>}
        <div className="flex flex-wrap gap-2">
          <Button type="submit">{t("common.save")}</Button>
          <Button variant="secondary" onClick={() => void download()}>
            {t("admin.app.build")}
          </Button>
        </div>
      </form>
    </Card>
  );
}
