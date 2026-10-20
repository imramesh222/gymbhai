/**
 * The pieces of Renew (PLAN.md §5.2, §17.5, §20.2): a numbered step, a plan
 * or a way to pay to pick, the bar with the total and the next thing to do,
 * and the screens for waiting, checking and done.
 */
import { ActivityIndicator, Pressable, View } from "react-native";

import { t } from "@shared/i18n";
import { formatRs, formatWholeRs } from "@shared/money";
import type { AccountKind, PaymentMethodAccount, Plan } from "@shared/types";
import { WALLET_BADGES } from "@shared/walletBadges";

import { colors, radius, space, tint } from "@/lib/theme";

import { useBrand } from "./brand";
import { Money } from "./Screen";
import { Button, Txt } from "./ui";

// --- steps -----------------------------------------------------------------------

/** A numbered step of the page; a tick once it's done, faded until it's reached. */
export function Step({
  n,
  title,
  done,
  reached = true,
  children,
}: {
  n: number;
  title: string;
  done: boolean;
  reached?: boolean;
  children?: React.ReactNode;
}) {
  const brand = useBrand();
  return (
    <View style={{ gap: space(3), opacity: reached ? 1 : 0.45 }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: space(2.5) }}>
        <View
          style={{
            width: 26,
            height: 26,
            borderRadius: 13,
            alignItems: "center",
            justifyContent: "center",
            backgroundColor: done ? brand : reached ? tint(brand, 0.12) : colors.track,
          }}
        >
          <Txt
            size={13}
            weight="bold"
            color={done ? "#ffffff" : reached ? brand : colors.faint}
          >
            {done ? "✓" : String(n)}
          </Txt>
        </View>
        <Txt weight="semibold" size={17} color={colors.ink} accessibilityRole="header">
          {title}
        </Txt>
      </View>
      {children}
    </View>
  );
}

// --- choosing --------------------------------------------------------------------

function Radio({ on }: { on: boolean }) {
  const brand = useBrand();
  return (
    <View
      style={{
        width: 22,
        height: 22,
        borderRadius: 11,
        borderWidth: 2,
        borderColor: on ? brand : "#cbd5e1",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {on ? (
        <View
          style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: brand }}
        />
      ) : null}
    </View>
  );
}

function Option({
  selected,
  onPress,
  label,
  testID,
  children,
}: {
  selected: boolean;
  onPress: () => void;
  label: string;
  testID?: string;
  children: React.ReactNode;
}) {
  const brand = useBrand();
  return (
    <Pressable
      testID={testID}
      accessibilityRole="radio"
      accessibilityLabel={label}
      accessibilityState={{ selected, checked: selected }}
      onPress={onPress}
      style={({ pressed }) => ({
        minHeight: 64,
        borderRadius: radius.lg,
        borderCurve: "continuous",
        paddingVertical: space(3.5),
        paddingHorizontal: space(4),
        borderWidth: selected ? 2 : 1,
        borderColor: selected ? brand : colors.hairline,
        backgroundColor: selected ? tint(brand, 0.06) : colors.surface,
        flexDirection: "row",
        alignItems: "center",
        gap: space(3),
        opacity: pressed ? 0.85 : 1,
        boxShadow: selected ? undefined : "0 1px 2px rgba(15, 23, 42, 0.04)",
      })}
    >
      {children}
    </Pressable>
  );
}

function Pill({
  label,
  color,
  background,
}: {
  label: string;
  color: string;
  background: string;
}) {
  return (
    <View
      style={{
        backgroundColor: background,
        borderRadius: 999,
        paddingHorizontal: space(2),
        paddingVertical: 2,
        alignSelf: "flex-start",
      }}
    >
      <Txt size={11} weight="bold" color={color} style={{ letterSpacing: 0.3 }}>
        {label}
      </Txt>
    </View>
  );
}

/** One plan: its name and what it gives, the price, and what it saves. */
export function PlanOption({
  plan,
  selected,
  onPress,
  monthly,
  saved,
  best,
}: {
  plan: Plan;
  selected: boolean;
  onPress: () => void;
  monthly: number | null;
  saved: number | null;
  best: boolean;
}) {
  const brand = useBrand();
  const extras = [
    plan.seats > 1 ? t("plans.forPeople", { count: plan.seats }) : null,
    monthly !== null && (plan.duration_months ?? 0) > 1
      ? t("app.renew.perMonth", { amount: formatWholeRs(monthly) })
      : null,
  ].filter(Boolean);
  return (
    <Option
      selected={selected}
      onPress={onPress}
      // The same words the Maestro flows tap: "1 month, Rs 2,500".
      label={`${plan.name}, ${formatRs(plan.price)}`}
    >
      <Radio on={selected} />
      <View style={{ flex: 1, gap: space(1) }}>
        <View
          style={{
            flexDirection: "row",
            alignItems: "center",
            gap: space(2),
            flexWrap: "wrap",
          }}
        >
          <Txt weight="semibold" size={16} color={colors.ink}>
            {plan.name}
          </Txt>
          {best ? (
            <Pill label={t("app.renew.bestValue")} color="#ffffff" background={brand} />
          ) : null}
        </View>
        {extras.length ? (
          <Txt size={13} color={colors.faint}>
            {extras.join(" · ")}
          </Txt>
        ) : null}
      </View>
      <View style={{ alignItems: "flex-end", gap: space(1) }}>
        <Money paisa={plan.price} weight="bold" size={17} color={colors.ink} />
        {saved !== null ? (
          <Txt size={12} weight="semibold" color={colors.green}>
            {t("app.renew.saveShort", { amount: formatWholeRs(saved) })}
          </Txt>
        ) : null}
      </View>
    </Option>
  );
}

export function WalletBadge({ kind, size = 40 }: { kind: AccountKind; size?: number }) {
  const badge = WALLET_BADGES[kind] ?? WALLET_BADGES.other;
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 4,
        borderCurve: "continuous",
        backgroundColor: badge.color,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Txt weight="bold" size={size * 0.45} color="#ffffff">
        {badge.letter}
      </Txt>
    </View>
  );
}

/** One of the gym's accounts: confirmed by the wallet itself, or by QR. */
export function MethodOption({
  method,
  selected,
  onPress,
}: {
  method: PaymentMethodAccount;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Option selected={selected} onPress={onPress} label={method.label}>
      <Radio on={selected} />
      <WalletBadge kind={method.kind} />
      <View style={{ flex: 1, gap: space(1) }}>
        <Txt weight="semibold" size={16} color={colors.ink}>
          {method.label}
        </Txt>
        {method.online ? (
          <Pill
            label={t("app.renew.instant")}
            color={colors.green}
            background={colors.greenBg}
          />
        ) : (
          <Txt size={13} color={colors.faint}>
            {t("app.renew.byQr")}
          </Txt>
        )}
      </View>
    </Option>
  );
}

// --- the bar ---------------------------------------------------------------------

/** The total and the one thing to do next, always in reach above the tabs. */
export function CheckoutBar({
  total,
  caption,
  children,
}: {
  total: number | null;
  caption: string;
  children: React.ReactNode;
}) {
  return (
    <View
      style={{
        backgroundColor: colors.surface,
        borderTopWidth: 1,
        borderTopColor: colors.hairline,
        paddingHorizontal: space(4),
        paddingTop: space(3),
        paddingBottom: space(3),
        flexDirection: "row",
        alignItems: "center",
        gap: space(4),
        boxShadow: "0 -4px 16px rgba(15, 23, 42, 0.06)",
      }}
    >
      <View style={{ minWidth: 92 }}>
        <Txt size={12} color={colors.faint} numberOfLines={1}>
          {caption}
        </Txt>
        {total !== null ? (
          <Money paisa={total} weight="bold" size={20} color={colors.ink} />
        ) : (
          <Txt weight="bold" size={20} color={colors.faint}>
            —
          </Txt>
        )}
      </View>
      <View style={{ flex: 1 }}>{children}</View>
    </View>
  );
}

// --- whole-screen states ---------------------------------------------------------

/** Waiting, checking, or done: one clear message and what can be done next. */
export function StatusPanel({
  tone,
  title,
  note,
  lines,
  primary,
  secondary,
  children,
}: {
  tone: "waiting" | "checking" | "done";
  title: string;
  note?: string;
  lines: { label: string; value: string }[];
  children?: React.ReactNode;
  primary?: { label: string; onPress: () => void; busy?: boolean; testID?: string };
  secondary?: { label: string; onPress: () => void; busy?: boolean; testID?: string };
}) {
  const brand = useBrand();
  const ring =
    tone === "done" ? colors.green : tone === "waiting" ? colors.amber : brand;
  return (
    <View
      style={{
        backgroundColor: colors.surface,
        borderRadius: radius.xl,
        borderCurve: "continuous",
        borderWidth: 1,
        borderColor: colors.hairline,
        padding: space(6),
        alignItems: "center",
        gap: space(4),
      }}
    >
      <View
        style={{
          width: 72,
          height: 72,
          borderRadius: 36,
          backgroundColor:
            tone === "done"
              ? colors.greenBg
              : tone === "waiting"
                ? colors.amberBg
                : tint(brand, 0.1),
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {tone === "checking" ? (
          <ActivityIndicator color={ring} size="large" />
        ) : (
          <Txt size={32} weight="bold" color={ring}>
            {tone === "done" ? "✓" : "⏳"}
          </Txt>
        )}
      </View>
      <Txt
        weight="bold"
        size={20}
        color={colors.ink}
        style={{ textAlign: "center" }}
        accessibilityRole="header"
      >
        {title}
      </Txt>
      {note ? (
        <Txt size={14} color={colors.muted} style={{ textAlign: "center" }}>
          {note}
        </Txt>
      ) : null}
      {lines.length ? (
        <View style={{ alignSelf: "stretch", gap: space(2), paddingTop: space(1) }}>
          {lines.map((line) => (
            <View
              key={line.label}
              style={{
                flexDirection: "row",
                justifyContent: "space-between",
                gap: space(3),
              }}
            >
              <Txt size={14} color={colors.faint}>
                {line.label}
              </Txt>
              <Txt
                selectable
                size={14}
                weight="medium"
                color={colors.ink}
                style={{ flexShrink: 1, textAlign: "right" }}
              >
                {line.value}
              </Txt>
            </View>
          ))}
        </View>
      ) : null}
      <View style={{ alignSelf: "stretch", gap: space(2), paddingTop: space(1) }}>
        {primary ? (
          <Button
            label={primary.label}
            onPress={primary.onPress}
            busy={primary.busy}
            testID={primary.testID}
          />
        ) : null}
        {secondary ? (
          <Button
            variant="secondary"
            label={secondary.label}
            onPress={secondary.onPress}
            busy={secondary.busy}
            testID={secondary.testID}
          />
        ) : null}
        {children}
      </View>
    </View>
  );
}
