"use client";

import { useEffect, useState } from "react";

import { QrCode } from "@/components/QrCode";
import { t } from "@/i18n";
import { memberCode, msUntilNext, type QrIdentity } from "@/lib/memberQr";

/** The member's own QR, redrawn every 30 seconds, computed on the phone. */
export function LiveQr({
  identity,
  size = 240,
}: {
  identity: QrIdentity;
  size?: number;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const code = memberCode(identity, now);
  return (
    <div className="flex flex-col items-center">
      <QrCode value={code} size={size} label={t("app.home.qrLabel")} />
      <p className="mt-2 text-xs text-slate-500">
        {t("app.home.qrChanges", {
          seconds: Math.ceil(msUntilNext(identity, now) / 1000),
        })}
      </p>
    </div>
  );
}
