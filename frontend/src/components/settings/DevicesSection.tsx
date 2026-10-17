"use client";

import Link from "next/link";

import { Button } from "@/components/Button";
import { Card } from "@/components/ui/Card";
import { t } from "@/i18n";
import { branchesApi, doorApi } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";
import { useConfirm } from "@/components/ui/ConfirmDialog";

/** Door scanners, and the posters and cards that go with them (§4.1, §4.3). */
export function DevicesSection() {
  const confirm = useConfirm();
  const { display } = useGymCalendar();
  const devices = useLoad(() => doorApi.devices(), []);
  const branches = useLoad(() => branchesApi.list(), []).data ?? [];
  return (
    <Card
      title={t("devices.title")}
      actions={
        <>
          <Link
            href="/kiosk"
            className="rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white"
          >
            {t("devices.useThis")}
          </Link>
          <Link
            href="/staff/settings/poster"
            className="rounded-xl bg-white px-3 py-2 text-sm font-semibold shadow-card ring-1 ring-hairline transition hover:bg-slate-50"
          >
            {t("devices.poster")}
          </Link>
        </>
      }
    >
      <p className="mb-2 text-sm text-slate-600">{t("devices.help")}</p>
      <ul className="divide-y divide-hairline text-sm">
        {devices.data?.map((d) => (
          <li key={d.id} className="flex items-center justify-between py-2">
            <span className={d.revoked_at ? "text-slate-500 line-through" : ""}>
              {d.name} · {branches.find((b) => b.id === d.branch_id)?.name}
              <span className="block text-xs text-slate-500">
                {d.last_seen_at
                  ? t("devices.lastSeen", {
                      when: formatDateTime(d.last_seen_at, display),
                    })
                  : t("devices.neverSeen")}
              </span>
            </span>
            {!d.revoked_at && (
              <Button
                variant="ghost"
                onClick={async () => {
                  const yes = await confirm({
                    title: t("devices.revoke"),
                    message: t("devices.revokeConfirm"),
                    confirmLabel: t("devices.revoke"),
                    danger: true,
                  });
                  if (!yes) return;
                  await doorApi.revokeDevice(d.id);
                  devices.reload();
                }}
              >
                {t("devices.revoke")}
              </Button>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
