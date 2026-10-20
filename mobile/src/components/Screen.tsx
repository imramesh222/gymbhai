import { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  RefreshControl,
  ScrollView,
  View,
  type StyleProp,
  type ViewStyle,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { t } from "@shared/i18n";
import { formatRs } from "@shared/money";

import { useOnline } from "@/lib/online";
import { colors, space } from "@/lib/theme";

import { Txt } from "./ui";

/**
 * A scrolling screen on the canvas colour. Pull down to re-read; the
 * keyboard never covers the field being typed in.
 */
export function Screen({
  children,
  onRefresh,
  style,
  topInset = false,
  footer,
  scrollRef,
}: {
  children: React.ReactNode;
  onRefresh?: () => Promise<unknown>;
  style?: StyleProp<ViewStyle>;
  /** Screens without a header pad for the status bar themselves. */
  topInset?: boolean;
  /** Stays at the bottom while the page scrolls: a total and its button. */
  footer?: React.ReactNode;
  scrollRef?: React.Ref<React.ComponentRef<typeof ScrollView>>;
}) {
  const insets = useSafeAreaInsets();
  const [refreshing, setRefreshing] = useState(false);
  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.canvas }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        ref={scrollRef}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
        // Below iOS's see-through navigation bar, not under it; screens
        // without one pad for the status bar themselves (topInset).
        contentInsetAdjustmentBehavior={topInset ? "never" : "automatic"}
        contentContainerStyle={[
          {
            padding: space(4),
            paddingTop: topInset ? insets.top + space(4) : space(4),
            paddingBottom: space(10),
            gap: space(4),
          },
          style,
        ]}
        refreshControl={
          onRefresh ? (
            <RefreshControl
              refreshing={refreshing}
              onRefresh={async () => {
                setRefreshing(true);
                await onRefresh().catch(() => undefined);
                setRefreshing(false);
              }}
            />
          ) : undefined
        }
      >
        {children}
      </ScrollView>
      {footer}
      {topInset ? (
        // The status bar over scrolled content: canvas, not text under the clock.
        <View
          pointerEvents="none"
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: insets.top,
            backgroundColor: colors.canvas,
          }}
        />
      ) : null}
    </KeyboardAvoidingView>
  );
}

/** No internet: say so, and that the QR still works (PLAN.md §17.5). */
export function OfflineBanner() {
  const online = useOnline();
  if (online) return null;
  return (
    <View
      accessibilityRole="alert"
      style={{
        backgroundColor: "#fef3c7",
        paddingVertical: space(2),
        paddingHorizontal: space(4),
      }}
    >
      <Txt
        size={13}
        weight="medium"
        color={colors.amberInk}
        style={{ textAlign: "center" }}
      >
        {t("app.offline")}
      </Txt>
    </View>
  );
}

export function Money({
  paisa,
  weight = "regular",
  size,
  color,
}: {
  paisa: number | null | undefined;
  weight?: "regular" | "medium" | "semibold" | "bold";
  size?: number;
  color?: string;
}) {
  return (
    <Txt
      weight={weight}
      size={size}
      color={color}
      style={{ fontVariant: ["tabular-nums"] }}
    >
      {formatRs(paisa)}
    </Txt>
  );
}
