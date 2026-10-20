/**
 * A value stepped with − and +: a day, or a number of days. Not the phone's
 * date picker, which only knows the AD calendar, while many gyms count and
 * show dates in BS.
 */
import { Pressable, View } from "react-native";

import { Label, Txt } from "./ui";
import { colors, radius, space } from "@/lib/theme";

export function Stepper({
  label,
  value,
  onLess,
  onMore,
  canLess,
  canMore = true,
}: {
  label: string;
  value: string;
  onLess: () => void;
  onMore: () => void;
  canLess: boolean;
  /** False at a limit: a progress check is never dated after today. */
  canMore?: boolean;
}) {
  const button = (
    text: string,
    onPress: () => void,
    enabled: boolean,
    name: string,
  ) => (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={name}
      accessibilityState={{ disabled: !enabled }}
      disabled={!enabled}
      onPress={onPress}
      style={{
        width: 48,
        height: 48,
        borderRadius: radius.md,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: colors.canvas,
        opacity: enabled ? 1 : 0.4,
      }}
    >
      <Txt weight="bold" size={22} color={colors.ink}>
        {text}
      </Txt>
    </Pressable>
  );
  return (
    <View style={{ gap: space(1.5) }}>
      <Label>{label}</Label>
      <View
        accessible={false}
        style={{ flexDirection: "row", alignItems: "center", gap: space(3) }}
      >
        {button("−", onLess, canLess, `${label} −`)}
        <Txt
          weight="semibold"
          style={{ flex: 1, textAlign: "center" }}
          accessibilityLiveRegion="polite"
        >
          {value}
        </Txt>
        {button("+", onMore, canMore, `${label} +`)}
      </View>
    </View>
  );
}
