/**
 * Home (PLAN.md §7, §17.5): days left, the QR for the door, how busy it is,
 * personal training (§18.3), visits, the latest notice. Everything here works from the saved copy with
 * no signal; the QR above all.
 */
import { router } from "expo-router";
import { Pressable, View } from "react-native";
import Svg, { Circle } from "react-native-svg";

import { describeHours } from "@shared/accessHours";
import { formatDate, type DateDisplay } from "@shared/dates";
import { plural, t, type MessageKey } from "@shared/i18n";
import type { MemberTraining } from "@shared/types";

import { useBrand } from "@/components/brand";
import { LiveQr } from "@/components/LiveQr";
import { PushPrompt } from "@/components/PushPrompt";
import { Money, Screen } from "@/components/Screen";
import { Button, Card, Label, LinkButton, Spinner, Txt } from "@/components/ui";
import { useMe } from "@/lib/hooks";
import { colors, radius, space } from "@/lib/theme";

const RING_RADIUS = 52;
const RING = 2 * Math.PI * RING_RADIUS;

function DaysRing({
  filled,
  color,
  days,
}: {
  filled: number;
  color: string;
  days: number;
}) {
  return (
    <View
      style={{
        width: 112,
        height: 112,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Svg
        width={112}
        height={112}
        viewBox="0 0 120 120"
        style={{ position: "absolute", transform: [{ rotate: "-90deg" }] }}
      >
        <Circle
          cx={60}
          cy={60}
          r={RING_RADIUS}
          fill="none"
          stroke={colors.track}
          strokeWidth={12}
        />
        <Circle
          cx={60}
          cy={60}
          r={RING_RADIUS}
          fill="none"
          stroke={color}
          strokeWidth={12}
          strokeLinecap="round"
          strokeDasharray={`${filled * RING} ${RING}`}
        />
      </Svg>
      <Txt weight="bold" size={30} color={colors.ink}>
        {days}
      </Txt>
    </View>
  );
}

const BUSY_COLOR = {
  quiet: colors.quiet,
  normal: colors.normal,
  busy: colors.busy,
} as const;

export default function Home() {
  const me = useMe();
  const brand = useBrand();
  if (!me.data) return <Spinner />;
  const { state, gym } = me.data;
  const active = state.status === "active" || state.status === "frozen";
  const filled = active ? Math.min(state.days_left / 30, 1) : 0;
  const ringColor = state.days_left <= 3 || !active ? colors.amber : brand;

  return (
    <Screen onRefresh={() => me.refetch()}>
      <Txt weight="bold" size={21} color={colors.ink}>
        {t("app.home.hello", { name: me.data.name.split(" ")[0] })}
      </Txt>

      <Card style={{ flexDirection: "row", alignItems: "center", gap: space(4) }}>
        <DaysRing
          filled={filled}
          color={ringColor}
          days={active ? state.days_left : 0}
        />
        <View style={{ flex: 1, gap: space(0.5) }}>
          <Label>
            {active
              ? t("app.home.daysLeft")
              : t(`app.home.status.${state.status}` as MessageKey)}
          </Label>
          {state.plan_name ? (
            <Txt weight="semibold" color={colors.ink}>
              {state.plan_name}
            </Txt>
          ) : null}
          {/* A family or couple plan (§19.1). */}
          {state.plan_with && state.plan_with.length > 0 ? (
            <Txt size={14} color={colors.muted}>
              {t("app.home.with", { names: state.plan_with.join(", ") })}
            </Txt>
          ) : null}
          {state.paid_by ? (
            <Txt size={14} color={colors.muted}>
              {t("app.home.paidBy", { name: state.paid_by })}
            </Txt>
          ) : null}
          {state.valid_until ? (
            <Txt size={14} color={colors.muted}>
              {state.status === "expired"
                ? t("app.home.expiredOn")
                : t("app.home.until")}{" "}
              {formatDate(state.valid_until, gym.date_display)}
            </Txt>
          ) : null}
          {state.visit_limit !== null && state.visits_left !== null ? (
            <Txt size={14} weight="medium">
              {t("app.home.visitsLeft", {
                left: state.visits_left,
                limit: state.visit_limit,
              })}
            </Txt>
          ) : null}
          {state.access_hours ? (
            <Txt size={13} color={colors.faint}>
              {t("app.home.hours", { hours: describeHours(state.access_hours) ?? "" })}
            </Txt>
          ) : null}
          {state.dues > 0 ? (
            <Owing label={t("app.home.owes")} paisa={state.dues} />
          ) : null}
          {state.group_dues ? (
            <Owing label={t("app.home.groupOwes")} paisa={state.group_dues} />
          ) : null}
        </View>
      </Card>

      {state.status === "active" ? (
        <LinkButton
          label={t("app.freeze.link")}
          color={colors.muted}
          onPress={() => router.push("/freeze")}
        />
      ) : null}

      {!active || state.days_left <= 7 ? (
        <Button label={t("app.home.renew")} onPress={() => router.navigate("/renew")} />
      ) : null}

      {/* The reason the app exists: one tap from opening it to the door. */}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={t("app.home.qrLabel")}
        accessibilityHint={t("mobile.qr.bigger")}
        onPress={() => router.push("/qr")}
        testID="qr-card"
        style={{
          backgroundColor: colors.surface,
          borderRadius: radius.xl,
          padding: space(5),
          alignItems: "center",
          gap: space(3),
          borderWidth: 1,
          borderColor: colors.hairline,
        }}
      >
        <Label>{t("app.home.showAtDoor")}</Label>
        <LiveQr identity={me.data.qr} size={220} />
        <View
          style={{
            backgroundColor: colors.canvas,
            borderRadius: 999,
            paddingHorizontal: space(3),
            paddingVertical: space(1),
          }}
        >
          <Txt size={13} color={colors.muted} style={{ letterSpacing: 1.5 }}>
            {me.data.member_code}
          </Txt>
        </View>
        <Txt size={13} color={brand} weight="medium">
          {t("mobile.qr.bigger")}
        </Txt>
      </Pressable>

      {me.data.busy ? (
        <Card style={{ flexDirection: "row", alignItems: "center", gap: space(3) }}>
          <View
            style={{
              width: 12,
              height: 12,
              borderRadius: 6,
              backgroundColor: BUSY_COLOR[me.data.busy],
            }}
          />
          <View style={{ flex: 1 }}>
            <Txt size={15} weight="semibold" color={colors.ink}>
              {t("app.busy.label")}: {t(`app.busy.${me.data.busy}` as MessageKey)}
            </Txt>
            <Txt size={13} color={colors.faint}>
              {t(`app.busy.hint.${me.data.busy}` as MessageKey)}
            </Txt>
          </View>
        </Card>
      ) : null}

      {/* Missing from a copy saved before personal training: nothing to show. */}
      {(me.data.training ?? []).map((pt) => (
        <Training key={pt.id} pt={pt} display={gym.date_display} />
      ))}

      <View style={{ flexDirection: "row", gap: space(3) }}>
        <Card style={{ flex: 1 }}>
          <Txt weight="bold" size={28} color={colors.ink}>
            {me.data.visits_this_month}
          </Txt>
          <Txt size={13} color={colors.faint}>
            {me.data.visits_this_month === 1
              ? t("app.home.visitThisMonth")
              : t("app.home.visitsThisMonth")}
          </Txt>
        </Card>
        <Card style={{ flex: 1 }}>
          <Txt weight="bold" size={28} color={colors.ink}>
            {me.data.streak_weeks}
          </Txt>
          <Txt size={13} color={colors.faint}>
            {t("app.home.streak")}
          </Txt>
        </Card>
      </View>

      <PushPrompt />

      <Pressable
        accessibilityRole="button"
        onPress={() => router.push("/progress")}
        style={{
          backgroundColor: colors.surface,
          borderRadius: radius.lg,
          padding: space(4),
          gap: space(1),
          borderWidth: 1,
          borderColor: colors.hairline,
        }}
      >
        <Txt weight="semibold" color={colors.ink}>
          {t("app.home.progress")}
        </Txt>
        <Txt size={14} color={colors.muted}>
          {t("app.home.progressHelp")}
        </Txt>
      </Pressable>

      {me.data.has_classes ? (
        <Pressable
          accessibilityRole="button"
          onPress={() => router.push("/classes")}
          style={{
            backgroundColor: colors.surface,
            borderRadius: radius.lg,
            padding: space(4),
            gap: space(1),
            borderWidth: 1,
            borderColor: colors.hairline,
          }}
        >
          <Txt weight="semibold" color={colors.ink}>
            {t("app.home.classes")}
          </Txt>
          <Txt size={14} color={colors.muted}>
            {t("app.home.classesHelp")}
          </Txt>
        </Pressable>
      ) : null}

      {me.data.latest_notice ? (
        <Pressable
          accessibilityRole="button"
          onPress={() => router.push("/notices")}
          style={{
            backgroundColor: colors.surface,
            borderRadius: radius.lg,
            padding: space(4),
            gap: space(1),
            borderWidth: 1,
            borderColor: colors.hairline,
          }}
        >
          <Label>{t("app.home.notice")}</Label>
          <Txt weight="semibold" color={colors.ink}>
            {me.data.latest_notice.title}
          </Txt>
          <Txt size={14} color={colors.muted} numberOfLines={2}>
            {me.data.latest_notice.body}
          </Txt>
        </Pressable>
      ) : null}
    </Screen>
  );
}

/** Their personal training: plan, trainer, sessions or days left (§18.3). */
function Training({ pt, display }: { pt: MemberTraining; display: DateDisplay }) {
  const until = formatDate(pt.end_date, display);
  return (
    <Card style={{ gap: space(0.5) }}>
      <Label>{t("app.home.training")}</Label>
      <Txt weight="semibold" color={colors.ink}>
        {pt.plan_name}
      </Txt>
      {pt.trainer_name ? (
        <Txt size={14} color={colors.muted}>
          {t("app.home.trainer", { name: pt.trainer_name })}
        </Txt>
      ) : null}
      <Txt size={14} weight="medium">
        {pt.status === "upcoming"
          ? t("app.home.trainingStarts", { date: formatDate(pt.start_date, display) })
          : pt.sessions !== null
            ? t("app.home.sessionsLeft", {
                left: pt.sessions_left ?? 0,
                total: pt.sessions,
              })
            : plural(
                pt.days_left,
                "app.home.trainingDays.one",
                "app.home.trainingDays.other",
                {
                  date: until,
                },
              )}
      </Txt>
      {pt.status === "active" && pt.sessions !== null ? (
        <Txt size={13} color={colors.faint}>
          {t("app.home.until")} {until}
        </Txt>
      ) : null}
      {pt.dues > 0 ? (
        <View
          style={{
            alignSelf: "flex-start",
            flexDirection: "row",
            gap: space(1),
            marginTop: space(1),
            backgroundColor: colors.amberBg,
            borderRadius: 999,
            paddingHorizontal: space(2.5),
            paddingVertical: space(1),
          }}
        >
          <Txt size={13} weight="semibold" color={colors.amberInk}>
            {t("app.home.owes")}
          </Txt>
          <Money paisa={pt.dues} size={13} weight="semibold" color={colors.amberInk} />
        </View>
      ) : null}
    </Card>
  );
}

/** Money still owed, as an amber pill. */
function Owing({ label, paisa }: { label: string; paisa: number }) {
  return (
    <View
      style={{
        alignSelf: "flex-start",
        flexDirection: "row",
        gap: space(1),
        marginTop: space(1),
        backgroundColor: colors.amberBg,
        borderRadius: 999,
        paddingHorizontal: space(2.5),
        paddingVertical: space(1),
      }}
    >
      <Txt size={13} weight="semibold" color={colors.amberInk}>
        {label}
      </Txt>
      <Money paisa={paisa} size={13} weight="semibold" color={colors.amberInk} />
    </View>
  );
}
