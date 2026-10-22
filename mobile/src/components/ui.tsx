/**
 * The app's building blocks. Touch targets are at least 44 points, text
 * grows with the phone's font size (to a limit, so layouts hold), and every
 * control has a label for screen readers (PLAN.md §17.5).
 */
import { useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  Text,
  TextInput,
  View,
  type PressableProps,
  type StyleProp,
  type TextInputProps,
  type TextProps,
  type TextStyle,
  type ViewStyle,
} from "react-native";

import { t } from "@shared/i18n";

import type { Action } from "@/lib/useAction";
import { colors, fontFamily, radius, space, tint, type Weight } from "@/lib/theme";

import { useBrand } from "./brand";

// --- text ------------------------------------------------------------------------

export function Txt({
  weight = "regular",
  size = 16,
  color = colors.text,
  style,
  ...props
}: TextProps & { weight?: Weight; size?: number; color?: string }) {
  return (
    <Text
      maxFontSizeMultiplier={1.6}
      {...props}
      style={[{ fontFamily: fontFamily(weight), fontSize: size, color }, style]}
    />
  );
}

export function Title({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: StyleProp<TextStyle>;
}) {
  return (
    <Txt
      weight="bold"
      size={22}
      color={colors.ink}
      accessibilityRole="header"
      style={style}
    >
      {children}
    </Txt>
  );
}

/** Small capitals above a card's content, as on the web. */
export function Label({ children }: { children: React.ReactNode }) {
  return (
    <Txt
      weight="semibold"
      size={12}
      color={colors.faint}
      style={{ textTransform: "uppercase", letterSpacing: 0.8 }}
    >
      {children}
    </Txt>
  );
}

// --- surfaces --------------------------------------------------------------------

export function Card({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <View
      style={[
        {
          backgroundColor: colors.surface,
          borderRadius: radius.lg,
          padding: space(4),
          borderWidth: 1,
          borderColor: colors.hairline,
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}

type Tone = "info" | "error" | "warning" | "success";
const TONES: Record<Tone, { bg: string; ink: string }> = {
  info: { bg: "#eff6ff", ink: "#1e3a8a" },
  error: { bg: colors.redBg, ink: colors.red },
  warning: { bg: colors.amberBg, ink: colors.amberInk },
  success: { bg: colors.greenBg, ink: colors.green },
};

export function Notice({
  tone = "info",
  children,
}: {
  tone?: Tone;
  children: React.ReactNode;
}) {
  return (
    <View
      accessibilityRole={tone === "error" ? "alert" : undefined}
      style={{
        backgroundColor: TONES[tone].bg,
        borderRadius: radius.md,
        padding: space(3),
      }}
    >
      <Txt size={14} color={TONES[tone].ink}>
        {children}
      </Txt>
    </View>
  );
}

// --- buttons ---------------------------------------------------------------------

type Variant = "primary" | "secondary" | "ghost" | "danger";

export function Button({
  label,
  onPress,
  variant = "primary",
  busy = false,
  disabled = false,
  accessibilityHint,
  style,
  testID,
}: {
  label: string;
  onPress: () => void;
  variant?: Variant;
  busy?: boolean;
  disabled?: boolean;
  accessibilityHint?: string;
  style?: StyleProp<ViewStyle>;
  testID?: string;
}) {
  const brand = useBrand();
  const off = disabled || busy;
  const background =
    variant === "primary"
      ? brand
      : variant === "danger"
        ? colors.red
        : variant === "secondary"
          ? colors.surface
          : "transparent";
  const ink =
    variant === "primary" || variant === "danger"
      ? "#ffffff"
      : variant === "secondary"
        ? colors.ink
        : brand;
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: off, busy }}
      disabled={off}
      onPress={onPress}
      style={({ pressed }) => [
        {
          minHeight: 50,
          borderRadius: radius.md,
          paddingHorizontal: space(5),
          alignItems: "center",
          justifyContent: "center",
          flexDirection: "row",
          gap: space(2),
          backgroundColor: background,
          borderWidth: variant === "secondary" ? 1 : 0,
          borderColor: colors.hairline,
          opacity: disabled && !busy ? 0.5 : pressed ? 0.85 : 1,
        },
        style,
      ]}
    >
      {busy && <ActivityIndicator color={ink} />}
      <Txt weight="semibold" color={ink}>
        {label}
      </Txt>
    </Pressable>
  );
}

/**
 * A button for something that changes data: runs through useAction, so a
 * double tap is one request (§17.4), and says when it's waiting for signal.
 */
export function ActionButton<A extends unknown[]>({
  action,
  args,
  label,
  variant,
  disabled,
  testID,
  style,
}: {
  action: Action<A>;
  args: A;
  label: string;
  variant?: Variant;
  disabled?: boolean;
  testID?: string;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <View style={[{ gap: space(2) }, style]}>
      <Button
        testID={testID}
        label={label}
        variant={variant}
        busy={action.busy}
        disabled={disabled}
        onPress={() => action.run(...args)}
      />
      <ActionStatus action={action} />
    </View>
  );
}

/** "Waiting for the internet" while it can't send; the error after. */
export function ActionStatus({
  action,
}: {
  action: Pick<Action<[]>, "waiting" | "error">;
}) {
  if (action.waiting)
    return <Notice tone="warning">{t("mobile.waitingToSend")}</Notice>;
  if (action.error) return <Notice tone="error">{action.error}</Notice>;
  return null;
}

/** A text link-like button, still 44 points tall. */
export function LinkButton({
  label,
  onPress,
  color,
  align = "center",
}: {
  label: string;
  onPress: () => void;
  color?: string;
  align?: "center" | "flex-start";
}) {
  const brand = useBrand();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      hitSlop={8}
      style={{ minHeight: 44, justifyContent: "center", alignItems: align }}
    >
      <Txt weight="semibold" size={15} color={color ?? brand}>
        {label}
      </Txt>
    </Pressable>
  );
}

/** One choice of several (plans, payment methods): a row that shows it's picked. */
export function ChoiceRow({
  selected,
  onPress,
  accessibilityLabel,
  children,
}: {
  selected: boolean;
  onPress: () => void;
  accessibilityLabel: string;
  children: React.ReactNode;
} & Pick<PressableProps, "testID">) {
  const brand = useBrand();
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ selected, checked: selected }}
      onPress={onPress}
      style={{
        minHeight: 56,
        borderRadius: radius.md,
        padding: space(3),
        borderWidth: selected ? 2 : 1,
        borderColor: selected ? brand : colors.hairline,
        backgroundColor: selected ? tint(brand, 0.08) : colors.surface,
        flexDirection: "row",
        alignItems: "center",
        gap: space(3),
      }}
    >
      {children}
    </Pressable>
  );
}

// --- inputs ----------------------------------------------------------------------

export function Field({
  label,
  help,
  value,
  onChangeText,
  style,
  ...props
}: TextInputProps & { label: string; help?: string }) {
  const [focused, setFocused] = useState(false);
  const brand = useBrand();
  return (
    <View style={[{ gap: space(1.5) }, style as StyleProp<ViewStyle>]}>
      <Txt weight="medium" size={14} color={colors.muted}>
        {label}
      </Txt>
      <TextInput
        accessibilityLabel={label}
        accessibilityHint={help}
        value={value}
        onChangeText={onChangeText}
        placeholderTextColor={colors.faint}
        maxFontSizeMultiplier={1.6}
        onFocus={(event) => {
          setFocused(true);
          props.onFocus?.(event);
        }}
        onBlur={(event) => {
          setFocused(false);
          props.onBlur?.(event);
        }}
        {...props}
        style={{
          minHeight: 50,
          borderRadius: radius.md,
          borderWidth: focused ? 2 : 1,
          borderColor: focused ? brand : colors.hairline,
          backgroundColor: colors.surface,
          paddingHorizontal: space(3.5),
          paddingVertical: props.multiline ? space(3) : 0,
          fontFamily: fontFamily("regular"),
          fontSize: 17,
          color: colors.ink,
          textAlignVertical: props.multiline ? "top" : "center",
        }}
      />
      {help ? (
        <Txt size={13} color={colors.faint}>
          {help}
        </Txt>
      ) : null}
    </View>
  );
}

export function Spinner() {
  return (
    <View style={{ padding: space(10), alignItems: "center" }}>
      <ActivityIndicator
        accessibilityLabel={t("common.loading")}
        color={colors.faint}
      />
    </View>
  );
}
