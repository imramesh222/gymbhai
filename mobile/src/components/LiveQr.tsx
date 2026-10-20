import { useEffect, useState } from "react";
import { View } from "react-native";

import { t } from "@shared/i18n";
import { memberCode, msUntilNext, type QrIdentity } from "@shared/qr/memberQr";

import { serverNow } from "@/lib/clock";
import { sign } from "@/lib/ed25519";
import { colors, space } from "@/lib/theme";

import { QrCode } from "./QrCode";
import { Txt } from "./ui";

/**
 * The member's own QR, computed on the phone from the key handed over at
 * sign-in (PLAN.md §4.2): no signal needed. Drawn at the server's time, so a
 * phone whose clock is a few minutes off still shows a code the door takes.
 */
export function LiveQr({
  identity,
  size,
  light = false,
}: {
  identity: QrIdentity;
  size: number;
  light?: boolean;
}) {
  const [now, setNow] = useState(serverNow);
  useEffect(() => {
    const timer = setInterval(() => setNow(serverNow()), 1000);
    return () => clearInterval(timer);
  }, []);
  const code = memberCode(identity, now, sign);
  return (
    <View style={{ alignItems: "center", gap: space(2) }}>
      <QrCode
        value={code}
        size={size}
        label={t("app.home.qrLabel")}
        testID="member-qr"
      />
      <Txt size={13} color={light ? "rgba(255,255,255,0.8)" : colors.faint}>
        {t("app.home.qrChanges", {
          seconds: Math.ceil(msUntilNext(identity, now) / 1000),
        })}
      </Txt>
    </View>
  );
}
