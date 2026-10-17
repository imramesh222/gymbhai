/**
 * The QR, big, at full brightness: what the door scanner reads best
 * (PLAN.md §17.5). The phone's brightness comes back on closing.
 */
import * as Brightness from "expo-brightness";
import { router } from "expo-router";
import { useEffect } from "react";
import { Platform, Pressable, useWindowDimensions, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { t } from "@shared/i18n";

import { Icon } from "@/components/Icon";
import { LiveQr } from "@/components/LiveQr";
import { Txt } from "@/components/ui";
import { useMe } from "@/lib/hooks";
import { space } from "@/lib/theme";

export default function FullQr() {
  const me = useMe().data;
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();

  useEffect(() => {
    let previous: number | null = null;
    void (async () => {
      try {
        previous = await Brightness.getBrightnessAsync();
        await Brightness.setBrightnessAsync(1);
      } catch {
        // Not allowed on this phone: the QR still shows.
      }
    })();
    return () => {
      void (async () => {
        try {
          if (Platform.OS === "android")
            await Brightness.restoreSystemBrightnessAsync();
          else if (previous !== null) await Brightness.setBrightnessAsync(previous);
        } catch {
          // Nothing to restore.
        }
      })();
    };
  }, []);

  return (
    <View
      style={{
        flex: 1,
        backgroundColor: "#ffffff",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {me ? (
        <View style={{ alignItems: "center", gap: space(4) }}>
          <Txt weight="semibold" size={18}>
            {me.name}
          </Txt>
          <LiveQr identity={me.qr} size={Math.min(width - space(12), 360)} />
          <Txt weight="medium" size={15} style={{ letterSpacing: 2 }}>
            {me.member_code}
          </Txt>
        </View>
      ) : null}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={t("common.close")}
        onPress={() => router.back()}
        testID="close-qr"
        style={{
          position: "absolute",
          top: insets.top + space(2),
          right: space(4),
          width: 48,
          height: 48,
          borderRadius: 24,
          backgroundColor: "#f1f5f9",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Icon name="close" color="#0f172a" />
      </Pressable>
    </View>
  );
}
