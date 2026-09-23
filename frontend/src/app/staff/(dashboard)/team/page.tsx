"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Card, PageHeader } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { Checkbox } from "@/components/ui/inputs";
import { t, type MessageKey } from "@/i18n";
import {
  branchesApi,
  errorMessage,
  staffApi,
  type Branch,
  type PermissionCatalog,
  type StaffMember,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useLoad } from "@/lib/useLoad";

const AREAS = [
  "members",
  "memberships",
  "payments",
  "reports",
  "door",
  "messages",
  "setup",
  "staff",
];
const PRESETS = ["manager", "front_desk", "blank"];

/** Staff accounts: the owner ticks exactly what each person may do (§2.1). */
export default function TeamPage() {
  const { me } = useAuth();
  const { data, reload } = useLoad(
    () => Promise.all([staffApi.list(), staffApi.catalog(), branchesApi.list()]),
    [],
  );
  const [editing, setEditing] = useState<StaffMember | "new" | null>(null);
  if (!data) return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
  const [staff, catalog, branches] = data;

  return (
    <div className="space-y-4">
      <PageHeader
        title={t("nav.staff")}
        actions={<Button onClick={() => setEditing("new")}>{t("team.add")}</Button>}
      />
      <Card>
        <ul className="divide-y divide-hairline">
          {staff.map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-3 py-3">
              <div className={`min-w-0 ${s.is_active ? "" : "opacity-50"}`}>
                <p className="font-medium">
                  {s.name}
                  {s.id === me?.staff.id && (
                    <span className="text-slate-500"> ({t("team.you")})</span>
                  )}
                </p>
                <p className="text-xs text-slate-500">
                  {[s.phone, s.email].filter(Boolean).join(" · ")}
                </p>
                <p className="text-xs text-slate-500">
                  {s.is_owner
                    ? t("team.owner")
                    : t("team.permissionCount", { count: s.permissions.length })}
                  {!s.is_active && ` · ${t("team.disabled")}`}
                  {s.branch_ids.length > 0 &&
                    ` · ${s.branch_ids.map((id) => branches.find((b) => b.id === id)?.name).join(", ")}`}
                </p>
              </div>
              {!s.is_owner && (
                <Button variant="secondary" onClick={() => setEditing(s)}>
                  {t("common.edit")}
                </Button>
              )}
            </li>
          ))}
        </ul>
      </Card>
      {editing && (
        <StaffDialog
          staff={editing === "new" ? null : editing}
          catalog={catalog}
          branches={branches}
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

function StaffDialog({
  staff,
  catalog,
  branches,
  onClose,
  onSaved,
}: {
  staff: StaffMember | null;
  catalog: PermissionCatalog;
  branches: Branch[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(staff?.name ?? "");
  const [phone, setPhone] = useState(staff?.phone ?? "");
  const [email, setEmail] = useState(staff?.email ?? "");
  const [password, setPassword] = useState("");
  const [permissions, setPermissions] = useState<string[]>(staff?.permissions ?? []);
  const [branchIds, setBranchIds] = useState<string[]>(staff?.branch_ids ?? []);
  const [active, setActive] = useState(staff?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);
  const grantable = new Set(catalog.grantable);

  function toggle(key: string, on: boolean) {
    setPermissions(on ? [...permissions, key] : permissions.filter((p) => p !== key));
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const body = {
      name,
      phone: phone || null,
      email: email || null,
      permissions,
      branch_ids: branchIds,
    };
    try {
      if (staff) {
        await staffApi.update(staff.id, { ...body, is_active: active });
        if (password) await staffApi.setPassword(staff.id, password);
      } else {
        await staffApi.create({ ...body, password });
      }
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Dialog open onClose={onClose} title={staff ? t("team.edit") : t("team.add")}>
      <form
        onSubmit={(e) => void save(e)}
        className="max-h-[75vh] space-y-3 overflow-y-auto"
      >
        <Field label={t("team.name")} value={name} onChange={setName} required />
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("team.phone")} value={phone} onChange={setPhone} type="tel" />
          <Field
            label={t("team.email")}
            value={email}
            onChange={setEmail}
            type="email"
          />
        </div>
        <Field
          label={staff ? t("team.newPassword") : t("team.password")}
          value={password}
          onChange={setPassword}
          type="password"
          autoComplete="new-password"
          required={!staff}
          help={staff ? t("team.newPasswordHelp") : t("signup.passwordHelp")}
        />

        <div>
          <h3 className="text-sm font-semibold">{t("team.permissions")}</h3>
          <div className="mt-2 flex flex-wrap gap-2">
            <span className="text-xs text-slate-500">{t("team.startFrom")}</span>
            {PRESETS.map((preset) => (
              <button
                key={preset}
                type="button"
                onClick={() =>
                  setPermissions(
                    catalog.presets[preset].filter((p) => grantable.has(p)),
                  )
                }
                className="rounded-full bg-white px-3 py-0.5 text-xs ring-1 ring-hairline transition hover:bg-slate-50"
              >
                {t(`team.preset.${preset}` as MessageKey)}
              </button>
            ))}
          </div>
          {AREAS.map((area) => {
            const keys = catalog.permissions.filter((p) => p.area === area);
            if (keys.length === 0) return null;
            return (
              <fieldset key={area} className="mt-3">
                <legend className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
                  {t(`perm.area.${area}` as MessageKey)}
                </legend>
                {keys.map(({ key }) => (
                  <Checkbox
                    key={key}
                    label={t(`perm.${key}` as MessageKey)}
                    checked={permissions.includes(key)}
                    disabled={!grantable.has(key)}
                    onChange={(on) => toggle(key, on)}
                  />
                ))}
              </fieldset>
            );
          })}
        </div>

        {branches.length > 1 && (
          <div>
            <h3 className="text-sm font-semibold">{t("team.branches")}</h3>
            <p className="text-xs text-slate-500">{t("team.branchesHelp")}</p>
            {branches.map((b) => (
              <Checkbox
                key={b.id}
                label={b.name}
                checked={branchIds.includes(b.id)}
                onChange={(on) =>
                  setBranchIds(
                    on ? [...branchIds, b.id] : branchIds.filter((id) => id !== b.id),
                  )
                }
              />
            ))}
          </div>
        )}
        {staff && (
          <Checkbox
            label={t("team.active")}
            checked={active}
            onChange={setActive}
            hint={t("team.activeHelp")}
          />
        )}
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block>
          {t("common.save")}
        </Button>
      </form>
    </Dialog>
  );
}
