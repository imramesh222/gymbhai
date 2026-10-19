/**
 * The camera, full screen, reading QR codes: the gym's poster (PLAN.md §17.5)
 * or the sign-in QR the desk shows (§18.4). What a code means is up to the
 * screen; this asks for the camera and handles one code at a time.
 */
import { CameraView, useCameraPermissions } from "expo-camera";
import { router } from "expo-router";
import { useRef, useState } from "react";
import { Linking, Pressable, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { t } from "@shared/i18n";

import { Icon } from "@/components/Icon";
import { Button, Notice, Txt } from "@/components/ui";
import { errorMessage } from "@/lib/errors";
import { space } from "@/lib/theme";

export function QrScanner({
  title,
  onCode,
}: {
  title: string;
  /** Resolves with a problem to show for a code that isn't the right kind. */
  onCode: (data: string) => Promise<string | void>;
}) {
  const insets = useSafeAreaInsets();
  const [permission, requestPermission] = useCameraPermissions();
  const [problem, setProblem] = useState<string | null>(null);
  // The camera reports the same code many times a second: one at a time.
  const busy = useRef(false);
  const lastBad = useRef<string | null>(null);

  async function scanned(data: string) {
    if (busy.current || data === lastBad.current) return;
    busy.current = true;
    try {
      const wrong = await onCode(data);
      if (wrong) {
        lastBad.current = data;
        setProblem(wrong);
      }
    } catch (error) {
      lastBad.current = data;
      setProblem(errorMessage(error));
    } finally {
      busy.current = false;
    }
  }

  const close = (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={t("common.close")}
      onPress={() => router.back()}
      hitSlop={12}
      style={{
        position: "absolute",
        top: insets.top + space(2),
        right: space(4),
        width: 44,
        height: 44,
        borderRadius: 22,
        backgroundColor: "rgba(0,0,0,0.45)",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Icon name="close" color="#ffffff" />
    </Pressable>
  );

  if (!permission?.granted) {
    return (
      <View
        style={{
          flex: 1,
          backgroundColor: "#0b1220",
          justifyContent: "center",
          padding: space(6),
          gap: space(4),
        }}
      >
        <Txt
          color="#ffffff"
          size={18}
          weight="semibold"
          style={{ textAlign: "center" }}
        >
          {t("mobile.scan.permission")}
        </Txt>
        {permission && !permission.canAskAgain ? (
          <Button
            label={t("mobile.openSettings")}
            onPress={() => void Linking.openSettings()}
          />
        ) : (
          <Button
            label={t("mobile.scan.allow")}
            onPress={() => void requestPermission()}
          />
        )}
        {close}
      </View>
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: "#000000" }}>
      <CameraView
        style={StyleSheet.absoluteFill}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
        onBarcodeScanned={({ data }) => void scanned(data)}
      />
      <View
        pointerEvents="none"
        style={{
          position: "absolute",
          alignSelf: "center",
          top: "28%",
          width: 240,
          height: 240,
          borderRadius: 24,
          borderWidth: 3,
          borderColor: "rgba(255,255,255,0.9)",
        }}
      />
      <View
        style={{
          position: "absolute",
          left: space(5),
          right: space(5),
          bottom: insets.bottom + space(8),
          gap: space(3),
        }}
      >
        <Txt color="#ffffff" weight="semibold" style={{ textAlign: "center" }}>
          {title}
        </Txt>
        {problem ? <Notice tone="warning">{problem}</Notice> : null}
      </View>
      {close}
    </View>
  );
}
