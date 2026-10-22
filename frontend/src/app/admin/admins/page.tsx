"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Card, PageHeader } from "@/components/ui/Card";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { Dialog } from "@/components/ui/Dialog";
import { Checkbox } from "@/components/ui/inputs";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { t, type MessageKey } from "@/i18n";
import {
  ADMIN_PERMISSIONS,
  adminApi,
  errorMessage,
  type AdminPermission,
  type PlatformAdmin,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/dates";
import { useLoad } from "@/lib/useLoad";

/** "admin.billing" → "admin.perm.billing", its name on the checklist. */
function permLabel(key: AdminPermission, hint = false): string {
  const name = key.split(".")[1];
  return t(`admin.perm.${name}${hint ? ".hint" : ""}` as MessageKey);
}

/**
 * Platform admins: the super admin adds the others and ticks what each may
 * do, as a gym's owner does for staff (PLAN.md §2.1, §7 /admin).
 */
export default function AdminAdminsPage() {
  const { me } = useAuth();
  const { data, reload } = useLoad(() => adminApi.admins(), []);
  const [editing, setEditing] = useState<PlatformAdmin | "new" | null>(null);
  if (!data) return <PageSkeleton label={t("common.loading")} />;

  return (
    <div className="space-y-4">
      <PageHeader
        title={t("admin.admins")}
        subtitle={t("admin.adminsHelp")}
        actions={
          <Button onClick={() => setEditing("new")}>{t("admin.addAdmin")}</Button>
        }
      />
      <Card>
        <ul className="divide-y divide-hairline">
          {data.map((admin) => (
            <li key={admin.id} className="flex items-center justify-between gap-3 py-3">
              <div className={`min-w-0 ${admin.is_active ? "" : "opacity-50"}`}>
                <p className="font-medium">
                  {admin.name}
                  {admin.id === me?.staff.id && (
                    <span className="text-slate-500"> ({t("team.you")})</span>
                  )}
                </p>
                <p className="text-xs text-slate-500">
                  {[admin.email, admin.phone].filter(Boolean).join(" · ")}
                </p>
                <p className="text-xs text-slate-500">
                  {admin.is_super_admin
                    ? t("admin.superAdmin")
                    : admin.permissions.map((key) => permLabel(key)).join(", ") ||
                      t("admin.gyms")}
                  {!admin.is_active && ` · ${t("team.disabled")}`}
                  {admin.two_step_enabled && ` · ${t("team.twoStepOn")}`}
                  {admin.last_login_at &&
                    ` · ${t("admin.lastSignIn")}: ${formatDateTime(admin.last_login_at, "ad")}`}
                </p>
              </div>
              {/* The super admin is changed only from the server. */}
              {!admin.is_super_admin && (
                <Button variant="secondary" onClick={() => setEditing(admin)}>
                  {t("common.edit")}
                </Button>
              )}
            </li>
          ))}
        </ul>
      </Card>
      {editing && (
        <AdminDialog
          admin={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
    </div>
  );
}

function AdminDialog({
  admin,
  onClose,
  onSaved,
}: {
  admin: PlatformAdmin | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const confirm = useConfirm();
  const toast = useToast();
  const [name, setName] = useState(admin?.name ?? "");
  const [email, setEmail] = useState(admin?.email ?? "");
  const [phone, setPhone] = useState(admin?.phone ?? "");
  const [password, setPassword] = useState("");
  const [permissions, setPermissions] = useState<AdminPermission[]>(
    admin?.permissions ?? [],
  );
  const [active, setActive] = useState(admin?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const body = { name, email: email || null, phone: phone || null, permissions };
    try {
      if (admin) {
        await adminApi.updateAdmin(admin.id, { ...body, is_active: active });
        if (password) await adminApi.adminPassword(admin.id, password);
        toast.success(t("common.saved"));
      } else {
        await adminApi.addAdmin({ ...body, password });
        toast.success(t("admin.adminAdded"));
      }
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title={admin ? t("admin.editAdmin") : t("admin.addAdmin")}
    >
      <form
        onSubmit={(e) => void save(e)}
        className="max-h-[75vh] space-y-3 overflow-y-auto"
      >
        <Field label={t("team.name")} value={name} onChange={setName} required />
        <div className="grid gap-3 sm:grid-cols-2">
          <Field
            label={t("team.email")}
            value={email}
            onChange={setEmail}
            type="email"
          />
          <Field label={t("team.phone")} value={phone} onChange={setPhone} type="tel" />
        </div>
        <Field
          label={admin ? t("team.newPassword") : t("team.password")}
          value={password}
          onChange={setPassword}
          type="password"
          autoComplete="new-password"
          required={!admin}
          help={admin ? t("team.newPasswordHelp") : t("admin.adminPasswordHelp")}
        />

        <fieldset>
          <legend className="text-sm font-semibold">{t("team.permissions")}</legend>
          {ADMIN_PERMISSIONS.map((key) => (
            <Checkbox
              key={key}
              label={permLabel(key)}
              hint={permLabel(key, true)}
              checked={permissions.includes(key)}
              onChange={(on) =>
                setPermissions(
                  on ? [...permissions, key] : permissions.filter((p) => p !== key),
                )
              }
            />
          ))}
        </fieldset>

        {admin && (
          <Checkbox
            label={t("team.active")}
            checked={active}
            onChange={setActive}
            hint={t("team.activeHelp")}
          />
        )}
        {admin?.two_step_enabled && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-50 px-3 py-2.5 text-sm">
            <span className="text-slate-700">{t("team.twoStepIsOn")}</span>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={async () => {
                const yes = await confirm({
                  title: t("team.resetTwoStep"),
                  message: t("team.resetTwoStepConfirm", { name: admin.name }),
                  confirmLabel: t("team.resetTwoStep"),
                  danger: true,
                });
                if (!yes) return;
                try {
                  await adminApi.resetAdminTwoStep(admin.id);
                  onSaved();
                } catch (err) {
                  setError(errorMessage(err));
                }
              }}
            >
              {t("team.resetTwoStep")}
            </Button>
          </div>
        )}
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block>
          {t("common.save")}
        </Button>
      </form>
    </Dialog>
  );
}
