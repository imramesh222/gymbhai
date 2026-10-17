"use client";

import { useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { Card } from "@/components/ui/Card";
import { t } from "@/i18n";
import { authApi, errorMessage, type DeviceSession } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/dates";
import { useLoad } from "@/lib/useLoad";
import { describeDevice } from "@/lib/userAgent";
import { useConfirm } from "@/components/ui/ConfirmDialog";

function deviceName(session: DeviceSession): string {
  const { browser, system } = describeDevice(session.user_agent);
  if (browser && system) return t("sessions.browserOn", { browser, system });
  return browser ?? system ?? t("sessions.unknown");
}

/**
 * My account → Devices (PLAN.md §16.1): everywhere this account is signed in.
 * A lost phone or a shared desk PC is signed out from here, at once.
 */
export function DevicesCard() {
  const confirm = useConfirm();
  const { me } = useAuth();
  const display = me?.gym?.settings.date_display ?? "ad";
  const { data, error, reload } = useLoad(() => authApi.sessions(), []);
  const [message, setMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);

  async function run(action: () => Promise<string>) {
    setMessage(null);
    try {
      setMessage({ tone: "success", text: await action() });
      reload();
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  const others = data?.filter((s) => !s.current) ?? [];
  return (
    <Card
      title={t("sessions.title")}
      actions={
        others.length > 0 && (
          <Button
            variant="secondary"
            size="sm"
            onClick={async () => {
              const yes = await confirm({
                title: t("sessions.signOutOthers"),
                message: t("sessions.signOutOthersConfirm"),
                confirmLabel: t("sessions.signOutOthers"),
              });
              if (!yes) return;
              void run(async () => {
                const { signed_out } = await authApi.signOutOthers();
                return t("sessions.signedOutOthers", { count: signed_out });
              });
            }}
          >
            {t("sessions.signOutOthers")}
          </Button>
        )
      }
    >
      {error && <Notice tone="error">{error}</Notice>}
      {!data && !error && (
        <p className="text-sm text-slate-500">{t("common.loading")}</p>
      )}
      <ul className="divide-y divide-hairline">
        {data?.map((session) => (
          <li key={session.id} className="flex items-center justify-between gap-3 py-3">
            <div className="min-w-0">
              <p className="font-medium text-slate-900">
                {deviceName(session)}
                {session.current && (
                  <span className="ml-2 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-800 ring-1 ring-emerald-600/20 ring-inset">
                    {t("sessions.thisDevice")}
                  </span>
                )}
              </p>
              <p className="text-xs text-slate-500">
                {[
                  session.ip,
                  session.last_used_at &&
                    t("sessions.lastUsed", {
                      when: formatDateTime(session.last_used_at, display),
                    }),
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </div>
            {!session.current && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  void run(async () => {
                    await authApi.signOutDevice(session.id);
                    return t("sessions.signedOut");
                  })
                }
              >
                {t("sessions.signOut")}
              </Button>
            )}
          </li>
        ))}
      </ul>
      {message && <Notice tone={message.tone}>{message.text}</Notice>}
    </Card>
  );
}
