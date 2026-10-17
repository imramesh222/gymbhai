/**
 * Renew (PLAN.md §5.2, §16.3 8.5, §17.5): Plan → Pay → Send proof, then
 * waiting for the gym, whose answer arrives live. The money goes to the gym's
 * own wallet or bank, never to GymBhai.
 */
import { useQueryClient } from "@tanstack/react-query";
import { Image } from "expo-image";
import { useState } from "react";
import { Alert, View } from "react-native";

import { formatDate } from "@shared/dates";
import { t } from "@shared/i18n";
import { formatRs } from "@shared/money";
import { perMonth, savings } from "@shared/planValue";
import type { Plan } from "@shared/types";

import { useBrand } from "@/components/brand";
import { Icon } from "@/components/Icon";
import { Money, Screen } from "@/components/Screen";
import {
  ActionButton,
  ActionStatus,
  Button,
  Card,
  ChoiceRow,
  Field,
  Label,
  Notice,
  Spinner,
  Title,
  Txt,
} from "@/components/ui";
import { apiUrl } from "@/lib/config";
import { useMe, usePayments, useRenewOptions } from "@/lib/hooks";
import { pickImage, saveToPhotos } from "@/lib/images";
import { memberApi, type UploadFile } from "@/lib/memberApi";
import { keys } from "@/lib/query";
import { useSlug } from "@/lib/session";
import { colors, radius, space } from "@/lib/theme";
import { useAction } from "@/lib/useAction";

function Steps({ at }: { at: 1 | 2 | 3 }) {
  const brand = useBrand();
  const labels = [
    t("app.renew.step.plan"),
    t("app.renew.step.pay"),
    t("app.renew.step.proof"),
  ];
  return (
    <View
      accessibilityLabel={t("app.renew.steps")}
      style={{ flexDirection: "row", gap: space(2) }}
    >
      {labels.map((label, i) => {
        const n = i + 1;
        const done = n < at;
        const current = n === at;
        return (
          <View
            key={label}
            accessibilityState={{ selected: current }}
            style={{
              flex: 1,
              flexDirection: "row",
              alignItems: "center",
              gap: space(1.5),
            }}
          >
            <View
              style={{
                width: 24,
                height: 24,
                borderRadius: 12,
                alignItems: "center",
                justifyContent: "center",
                backgroundColor: done || current ? brand : colors.track,
              }}
            >
              <Txt
                size={12}
                weight="semibold"
                color={done || current ? "#ffffff" : colors.faint}
              >
                {done ? "✓" : String(n)}
              </Txt>
            </View>
            <Txt
              size={13}
              weight="semibold"
              color={n > at ? colors.faint : colors.ink}
              numberOfLines={1}
            >
              {label}
            </Txt>
          </View>
        );
      })}
    </View>
  );
}

export default function Renew() {
  const slug = useSlug();
  const queryClient = useQueryClient();
  const me = useMe().data;
  const options = useRenewOptions();
  const mine = usePayments();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [methodId, setMethodId] = useState<string | null>(null);
  const [ref, setRef] = useState("");
  const [screenshot, setScreenshot] = useState<UploadFile | null>(null);
  const [needProof, setNeedProof] = useState(false);
  // "Recent" is measured from when the screen opened.
  const [openedAt] = useState(Date.now);

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: keys.payments(slug) }),
      queryClient.invalidateQueries({ queryKey: keys.renew(slug) }),
      queryClient.invalidateQueries({ queryKey: keys.me(slug) }),
    ]);

  const admission = options.data?.first_membership ? (plan?.admission_fee ?? 0) : 0;
  const total = (plan?.price ?? 0) + admission;

  // One request, however many taps or retries (§17.4). A screenshot upload
  // that failed is sent again with the request's replayed answer.
  const send = useAction(
    async (
      key: string,
      body: {
        plan_id: string;
        payment_method_id: string | null;
        amount: number;
        transaction_ref: string | null;
      },
    ) => {
      const created = await memberApi.createRequest(body, key);
      if (screenshot) await memberApi.uploadScreenshot(created.id, screenshot);
      return created;
    },
    {
      onSuccess: () => {
        setPlan(null);
        setMethodId(null);
        setRef("");
        setScreenshot(null);
        void refresh();
      },
    },
  );

  const waiting = mine.data?.requests.find((r) => r.status === "pending");
  const withdraw = useAction((key: string, id: string) => memberApi.withdraw(id, key), {
    onSuccess: () => void refresh(),
  });

  const savePhoto = useAction((_key: string, path: string) => saveToPhotos(path), {
    onSuccess: () => Alert.alert(t("mobile.renew.qrSaved")),
  });

  const choose = useAction(async (_key: string, from: "gallery" | "camera") => {
    const file = await pickImage(from, "screenshot.jpg");
    if (file) {
      setScreenshot(file);
      setNeedProof(false);
    }
  });

  if (!me || !options.data || !mine.data) return <Spinner />;
  const display = me.gym.date_display;

  if (waiting) {
    return (
      <Screen onRefresh={refresh}>
        <Card
          style={{ alignItems: "center", gap: space(3), paddingVertical: space(8) }}
        >
          <Txt size={40}>⏳</Txt>
          <Title style={{ textAlign: "center" }}>{t("app.renew.waiting")}</Title>
          <Txt color={colors.muted} style={{ textAlign: "center" }}>
            {t("app.renew.waitingDetail", { plan: waiting.plan_name ?? "" })}{" "}
            {formatRs(waiting.amount)}
          </Txt>
          <ActionButton
            action={withdraw}
            args={[waiting.id]}
            variant="secondary"
            label={t("app.renew.withdraw")}
            testID="withdraw"
            style={{ alignSelf: "stretch" }}
          />
        </Card>
      </Screen>
    );
  }

  const { plans, payment_methods: methods } = options.data;
  const method = methods.find((m) => m.id === methodId);
  // The gym's latest answer, while it's news (the last two days).
  const answered = mine.data.requests.find(
    (r) => r.status === "approved" || r.status === "rejected",
  );
  const recent =
    answered?.reviewed_at &&
    openedAt - Date.parse(answered.reviewed_at) < 2 * 24 * 3600 * 1000;
  const lastRejected = answered?.status === "rejected" ? answered : undefined;
  const lastApproved = recent && answered?.status === "approved" ? answered : undefined;

  return (
    <Screen onRefresh={refresh}>
      <Title>{t("app.renew.title")}</Title>
      <Steps at={!plan ? 1 : !methodId ? 2 : 3} />
      {lastApproved ? (
        <Notice tone="success">
          {t("mobile.renew.confirmed", { plan: lastApproved.plan_name ?? "" })}
        </Notice>
      ) : null}
      {lastRejected ? (
        <Notice tone="warning">
          {t("app.renew.rejected", { reason: lastRejected.reject_reason ?? "" })}
        </Notice>
      ) : null}
      <Txt size={14} color={colors.muted}>
        {t("app.renew.startsOn", {
          date: formatDate(options.data.renewal_starts_on, display),
        })}
      </Txt>

      <View style={{ gap: space(2) }} accessibilityRole="radiogroup">
        <Label>{t("app.renew.choosePlan")}</Label>
        {plans.map((p) => {
          const monthly = perMonth(p);
          const saved = savings(p, plans);
          return (
            <ChoiceRow
              key={p.id}
              selected={plan?.id === p.id}
              onPress={() => setPlan(p)}
              accessibilityLabel={`${p.name}, ${formatRs(p.price)}`}
            >
              <View style={{ flex: 1 }}>
                <Txt weight="medium">{p.name}</Txt>
                {monthly !== null && (p.duration_months ?? 0) > 1 ? (
                  <Txt size={13} color={colors.faint}>
                    {t("app.renew.perMonth", { amount: formatRs(monthly) })}
                  </Txt>
                ) : null}
              </View>
              <View style={{ alignItems: "flex-end", gap: space(1) }}>
                <Money paisa={p.price} weight="semibold" />
                {saved !== null ? (
                  <View
                    style={{
                      backgroundColor: colors.greenBg,
                      borderRadius: 999,
                      paddingHorizontal: space(2),
                      paddingVertical: 2,
                    }}
                  >
                    <Txt size={12} weight="semibold" color={colors.green}>
                      {t("app.renew.save", { amount: formatRs(saved) })}
                    </Txt>
                  </View>
                ) : null}
              </View>
            </ChoiceRow>
          );
        })}
      </View>

      {plan ? (
        <>
          <Card style={{ gap: space(1) }}>
            {admission > 0 ? (
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Txt size={14}>{t("sale.admissionFee")}</Txt>
                <Money paisa={admission} size={14} />
              </View>
            ) : null}
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <Txt weight="semibold">{t("app.renew.pay")}</Txt>
              <Money paisa={total} weight="semibold" />
            </View>
          </Card>

          <View style={{ gap: space(2) }}>
            <Label>{t("app.renew.payTo")}</Label>
            {methods.length === 0 ? <Notice>{t("app.renew.noMethods")}</Notice> : null}
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: space(2) }}>
              {methods.map((m) => (
                <ChoiceRow
                  key={m.id}
                  selected={methodId === m.id}
                  onPress={() => setMethodId(m.id)}
                  accessibilityLabel={m.label}
                >
                  <Txt weight={methodId === m.id ? "semibold" : "regular"}>
                    {m.label}
                  </Txt>
                </ChoiceRow>
              ))}
            </View>
            {method ? (
              <Card style={{ alignItems: "center", gap: space(2) }}>
                {method.qr_image_url ? (
                  <>
                    <Image
                      source={{ uri: apiUrl(method.qr_image_url) }}
                      contentFit="contain"
                      accessibilityLabel={method.label}
                      style={{ width: 240, height: 240, borderRadius: radius.md }}
                    />
                    <Button
                      variant="secondary"
                      label={t("mobile.renew.saveQr")}
                      busy={savePhoto.busy}
                      onPress={() => savePhoto.run(method.qr_image_url!)}
                    />
                    <ActionStatus action={savePhoto} />
                  </>
                ) : null}
                {method.account_name ? (
                  <Txt weight="medium">{method.account_name}</Txt>
                ) : null}
                {method.account_number ? (
                  <Txt selectable color={colors.muted}>
                    {method.account_number}
                  </Txt>
                ) : null}
                <Txt size={13} color={colors.faint} style={{ textAlign: "center" }}>
                  {t("app.renew.payInWallet")}
                </Txt>
              </Card>
            ) : null}
          </View>

          <Card style={{ gap: space(4) }}>
            <Field
              label={t("payment.transactionRef")}
              help={t("app.renew.refHelp")}
              value={ref}
              onChangeText={(value) => {
                setRef(value);
                setNeedProof(false);
              }}
              autoCapitalize="characters"
              autoCorrect={false}
              testID="transaction-ref"
            />
            <View style={{ gap: space(2) }}>
              <Txt weight="medium" size={14} color={colors.muted}>
                {t("app.renew.screenshot")}
              </Txt>
              {screenshot ? (
                <View
                  style={{ flexDirection: "row", alignItems: "center", gap: space(3) }}
                >
                  <Image
                    source={{ uri: screenshot.uri }}
                    style={{ width: 56, height: 96, borderRadius: radius.sm }}
                  />
                  <Txt size={14} style={{ flex: 1 }}>
                    {t("mobile.renew.screenshotAdded")}
                  </Txt>
                  <Button
                    variant="ghost"
                    label={t("mobile.remove")}
                    onPress={() => setScreenshot(null)}
                  />
                </View>
              ) : (
                <ChoiceRow
                  selected={false}
                  onPress={() => choose.run("gallery")}
                  accessibilityLabel={t("mobile.renew.pickScreenshot")}
                >
                  <Icon name="image" color={colors.muted} />
                  <Txt>{t("mobile.renew.pickScreenshot")}</Txt>
                </ChoiceRow>
              )}
            </View>
            {needProof ? (
              <Notice tone="error">{t("app.renew.needProof")}</Notice>
            ) : null}
            <Button
              testID="ive-paid"
              label={t("app.renew.sent")}
              busy={send.busy}
              onPress={() => {
                // A transaction ID or a screenshot, before anything is sent.
                if (!ref.trim() && !screenshot) return setNeedProof(true);
                send.run({
                  plan_id: plan.id,
                  payment_method_id: methodId,
                  amount: total,
                  transaction_ref: ref.trim() || null,
                });
              }}
            />
            <ActionStatus action={send} />
          </Card>
        </>
      ) : null}
    </Screen>
  );
}
