"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { Card } from "@/components/ui/Card";
import { Checkbox } from "@/components/ui/inputs";
import { t, type MessageKey } from "@/i18n";
import { accessApi, doorApi, errorMessage, type MemberDetail } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/dates";
import { useGymCalendar } from "@/lib/gym";
import { useLoad } from "@/lib/useLoad";

/** App access and the door, on the member's profile (§5.5, §7). */
export function AccessCard({
  member,
  onChanged,
}: {
  member: MemberDetail;
  onChanged: () => void;
}) {
  const { can } = useAuth();
  const { display } = useGymCalendar();
  const visits = useLoad(
    () =>
      can("members.view")
        ? doorApi.checkIns({ member_id: member.id, limit: 10 })
        : Promise.resolve({ items: [], total: 0 }),
    [member.id],
  );
  const [message, setMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);

  async function run(
    action: () => Promise<unknown>,
    done: MessageKey,
    confirm?: MessageKey,
  ) {
    if (confirm && !window.confirm(t(confirm))) return;
    try {
      await action();
      setMessage({ tone: "success", text: t(done) });
      onChanged();
    } catch (err) {
      setMessage({ tone: "error", text: errorMessage(err) });
    }
  }

  return (
    <Card title={t("access.title")}>
      <div className="space-y-2">
        {can("members.app_access") && (
          <>
            <Checkbox
              label={t("access.appAccess")}
              checked={member.app_access}
              hint={t("access.appAccessHelp")}
              onChange={(on) =>
                run(() => accessApi.setAccess(member.id, on), "common.saved")
              }
            />
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                onClick={() =>
                  run(() => accessApi.resendWelcome(member.id), "access.welcomeSent")
                }
              >
                {t("access.resendWelcome")}
              </Button>
              <Button
                variant="secondary"
                onClick={() =>
                  run(
                    () => accessApi.signOutAll(member.id),
                    "access.signedOut",
                    "access.signOutConfirm",
                  )
                }
              >
                {t("access.signOutAll")}
              </Button>
              <Button
                variant="secondary"
                onClick={() =>
                  run(
                    () => accessApi.reissueQr(member.id),
                    "access.qrReissued",
                    "access.reissueConfirm",
                  )
                }
              >
                {t("access.reissueQr")}
              </Button>
            </div>
          </>
        )}
        {can("members.edit") && (
          <Link
            href={`/staff/members/${member.id}/card`}
            className="inline-block text-sm font-medium text-brand-700 hover:underline"
          >
            {t("access.printCard")}
          </Link>
        )}
        {message && <Notice tone={message.tone}>{message.text}</Notice>}
        {visits.data && visits.data.items.length > 0 && (
          <div className="pt-2">
            <h3 className="text-sm font-semibold">
              {t("access.recentVisits", { count: visits.data.total })}
            </h3>
            <ul className="mt-1 space-y-0.5 text-xs text-slate-600">
              {visits.data.items.map((c) => (
                <li key={c.id}>
                  {formatDateTime(c.at, display)} ·{" "}
                  <span className={c.result.startsWith("denied") ? "text-red-700" : ""}>
                    {t(`door.result.${c.result}` as MessageKey)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}
