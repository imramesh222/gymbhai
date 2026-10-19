"use client";

import { CheckCircle2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/Button";
import { Notice } from "@/components/Notice";
import { QrCode } from "@/components/QrCode";
import { Dialog } from "@/components/ui/Dialog";
import { t } from "@/i18n";
import { accessApi } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";

function minutesAndSeconds(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/**
 * Sign a member in on their phone at the desk, with no SMS code (PLAN.md
 * §18.4): a QR they scan with the phone's camera, or with "Scan the QR at the
 * desk" in the app. It works once, for a few minutes. The profile behind
 * reloads live when they sign in, and `signedInAt` moves past the QR's.
 */
export function SignInQr({
  memberId,
  name,
  signedInAt,
  onClose,
}: {
  memberId: string;
  name: string;
  signedInAt: string | null;
  onClose: () => void;
}) {
  const [round, setRound] = useState(0);
  // When it arrived, on this screen's own clock: a desk PC set to the wrong
  // time still counts down the right minutes.
  const { data: link, error } = useLoad(async () => {
    const made = await accessApi.signInLink(memberId);
    return { ...made, shownAt: Date.now() };
  }, [memberId, round]);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Both of these times are the server's.
  const done =
    link !== null &&
    signedInAt !== null &&
    Date.parse(signedInAt) >= Date.parse(link.made_at);
  const lasts = link
    ? (Date.parse(link.expires_at) - Date.parse(link.made_at)) / 1000
    : 0;
  const left = link
    ? Math.max(0, Math.min(lasts, Math.round(lasts - (now - link.shownAt) / 1000)))
    : 0;

  return (
    <Dialog open onClose={onClose} title={t("access.signInPhone")}>
      <div className="space-y-4 text-center">
        {done ? (
          <>
            <CheckCircle2 className="mx-auto size-14 text-emerald-600" aria-hidden />
            <p className="font-semibold text-slate-900" role="status">
              {t("access.signedInThere", { name })}
            </p>
            <Button block onClick={onClose}>
              {t("common.close")}
            </Button>
          </>
        ) : link && left > 0 ? (
          <>
            <div className="flex justify-center">
              <QrCode
                value={link.url}
                size={240}
                label={t("access.signInQr", { name })}
              />
            </div>
            <p className="text-sm text-slate-600">{t("access.signInHelp", { name })}</p>
            <p className="text-sm font-medium text-slate-900 tabular-nums">
              {t("access.signInLeft", { time: minutesAndSeconds(left) })}
            </p>
          </>
        ) : link ? (
          <>
            <p className="text-sm text-slate-600">{t("access.signInExpired")}</p>
            <Button block onClick={() => setRound((n) => n + 1)}>
              {t("access.signInAgain")}
            </Button>
          </>
        ) : null}
        {error && <Notice tone="error">{error}</Notice>}
      </div>
    </Dialog>
  );
}
