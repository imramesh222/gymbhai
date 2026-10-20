/**
 * Renew (PLAN.md §5.2, §16.3 8.5, §17.5, §20.2): choose a plan, choose how to
 * pay, pay. Nothing is chosen for the member. A wallet the gym's account is
 * confirmed by takes them to its own page and back; any other way shows the
 * gym's QR, then the transaction ID or a screenshot. The total and the next
 * step stay in a bar at the bottom. The money goes to the gym's own wallet or
 * bank, never to GymBhai.
 */
import { useQueryClient } from "@tanstack/react-query";
import { Image } from "expo-image";
import { router } from "expo-router";
import { useEffect, useRef, useState } from "react";
import {
  Alert,
  AppState,
  Linking,
  Pressable,
  View,
  type ScrollView,
} from "react-native";

import { formatDate, formatDateTime } from "@shared/dates";
import { t, type MessageKey } from "@shared/i18n";
import { formatRs } from "@shared/money";
import { bestValue, perMonth, savings } from "@shared/planValue";
import type { OnlinePayment, Plan } from "@shared/types";

import { useBrand } from "@/components/brand";
import { Icon } from "@/components/Icon";
import {
  CheckoutBar,
  MethodOption,
  PlanOption,
  StatusPanel,
  Step,
  WalletBadge,
} from "@/components/RenewParts";
import { Money, Screen } from "@/components/Screen";
import {
  ActionStatus,
  Button,
  Card,
  Field,
  Label,
  LinkButton,
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

// Back from the wallet's page: asked this often, for this long, then the
// member asks again by hand (the worker keeps asking anyway).
const CHECK_EVERY_MS = 5000;
const CHECKS = 24;

type Started = {
  id: string;
  wallet: string;
  url: string;
  plan: string;
  amount: number;
  at: number;
};

export default function Renew() {
  const brand = useBrand();
  const slug = useSlug();
  const queryClient = useQueryClient();
  const me = useMe().data;
  const options = useRenewOptions();
  const mine = usePayments();
  const scroll = useRef<React.ComponentRef<typeof ScrollView>>(null);
  const where = useRef({ pay: 0, finish: 0 });
  const [plan, setPlan] = useState<Plan | null>(null);
  const [methodId, setMethodId] = useState<string | null>(null);
  const [ref, setRef] = useState("");
  const [screenshot, setScreenshot] = useState<UploadFile | null>(null);
  const [needProof, setNeedProof] = useState(false);
  // An account the wallet confirms (§20.2): its page, unless they'd rather
  // pay the QR and send the transaction ID.
  const [byHand, setByHand] = useState(false);
  // A wallet payment they left the app for, and what the wallet last said.
  const [started, setStarted] = useState<Started | null>(null);
  const [outcome, setOutcome] = useState<OnlinePayment | null>(null);
  const checks = useRef(0);
  // Asked as long as it's worth asking: then "Check again" is theirs.
  const [gaveUp, setGaveUp] = useState(false);
  // "You're renewed" is for an answer that came while the screen was open.
  const [openedAt] = useState(Date.now);
  const [seen, setSeen] = useState<string | null>(null);

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: keys.payments(slug) }),
      queryClient.invalidateQueries({ queryKey: keys.renew(slug) }),
      queryClient.invalidateQueries({ queryKey: keys.me(slug) }),
    ]);

  /** Back to an empty page: nothing chosen for them, ever. */
  function clear() {
    setPlan(null);
    setMethodId(null);
    setRef("");
    setScreenshot(null);
    setNeedProof(false);
    setByHand(false);
  }

  function scrollTo(y: number) {
    setTimeout(() => scroll.current?.scrollTo({ y: Math.max(0, y - space(3)) }), 60);
  }

  // Whoever pays for a family or couple plan renews it for everyone on it
  // (§19.1): each newcomer's admission fee too.
  const mates = plan && plan.seats > 1 ? (options.data?.renew_with ?? []) : [];
  const newcomers =
    (options.data?.first_membership ? 1 : 0) +
    mates.filter((m) => m.first_membership).length;
  const admission = (plan?.admission_fee ?? 0) * newcomers;
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
        clear();
        void refresh();
      },
    },
  );

  // The wallet's page in the phone's browser; it comes back to this app's
  // Renew, and the screen asks the wallet how it went.
  const payOnline = useAction(
    async (
      _key: string,
      body: { plan_id: string; payment_method_id: string },
      wallet: string,
    ) => {
      const begun = await memberApi.startOnlinePayment(body);
      checks.current = 0;
      setGaveUp(false);
      setOutcome(null);
      setStarted({
        id: begun.id,
        wallet,
        url: begun.pay_url,
        plan: begun.plan_name,
        amount: begun.amount,
        at: Date.now(),
      });
      await Linking.openURL(begun.pay_url);
      return begun;
    },
  );

  const check = useAction(
    (_key: string, id: string) => memberApi.checkOnlinePayment(id),
    {
      offline: "run",
      onSuccess: (answer) => {
        setOutcome(answer);
        if (answer.status === "started") return;
        setStarted(null);
        if (answer.approved || answer.waiting_for_desk) clear();
        void refresh();
      },
    },
  );

  // Asked afresh whenever the app comes back from the wallet, then every few
  // seconds for a while, but only while the app is on screen: in the
  // background there's nobody to tell, and the tries would run out unpaid.
  const startedId = started?.id;
  useEffect(() => {
    if (!startedId) return;
    const ask = (fresh = false) => {
      if (AppState.currentState !== "active") return;
      if (fresh) {
        checks.current = 0;
        setGaveUp(false);
      }
      if (checks.current >= CHECKS) return setGaveUp(true);
      checks.current += 1;
      check.run(startedId);
    };
    const back = AppState.addEventListener("change", (state) => {
      if (state === "active") ask(true);
    });
    const timer = setInterval(() => ask(), CHECK_EVERY_MS);
    return () => {
      back.remove();
      clearInterval(timer);
    };
    // `check` is a new object each render; the payment is what matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startedId]);

  const waiting = mine.data?.requests.find((r) => r.status === "pending");
  // The gym's answer can arrive live before any check does: then the
  // payment is settled, approved or waiting for the desk.
  const startedAt = started?.at ?? null;
  const settledLive = Boolean(
    startedAt !== null &&
    mine.data?.requests.some(
      (r) =>
        r.status === "pending" ||
        (r.status === "approved" &&
          r.reviewed_at !== null &&
          Date.parse(r.reviewed_at) >= startedAt - 60_000),
    ),
  );
  // Still away paying, as far as the screen is concerned.
  const away = settledLive ? null : started;
  const withdraw = useAction((key: string, id: string) => memberApi.withdraw(id, key), {
    onSuccess: () => {
      clear();
      void refresh();
    },
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
  const state = me.state;

  // --- whole-screen states -----------------------------------------------------

  if (away) {
    return (
      <Screen onRefresh={refresh}>
        <StatusPanel
          tone="checking"
          title={t("pay.checking", { wallet: away.wallet })}
          note={gaveUp ? t("pay.notYet", { wallet: away.wallet }) : undefined}
          lines={[
            { label: t("app.renew.planLine"), value: away.plan },
            { label: t("app.renew.amountLine"), value: formatRs(away.amount) },
          ]}
          primary={{
            label: t("pay.checkAgain"),
            busy: check.busy,
            onPress: () => {
              checks.current = 0;
              setGaveUp(false);
              check.run(away.id);
            },
          }}
          secondary={{
            label: t("app.renew.openAgain", { wallet: away.wallet }),
            onPress: () => void Linking.openURL(away.url),
          }}
        >
          <LinkButton
            label={t("app.renew.backToPlans")}
            onPress={() => setStarted(null)}
          />
        </StatusPanel>
        <ActionStatus action={check} />
      </Screen>
    );
  }

  if (waiting) {
    const wallet = waiting.confirmed_by
      ? t(`account.${waiting.confirmed_by}` as MessageKey)
      : null;
    return (
      <Screen onRefresh={refresh}>
        <StatusPanel
          tone="waiting"
          title={wallet ? t("pay.paidForDesk") : t("app.renew.waiting")}
          note={wallet ? undefined : t("app.renew.waitingNote")}
          lines={[
            { label: t("app.renew.planLine"), value: waiting.plan_name ?? "" },
            { label: t("app.renew.amountLine"), value: formatRs(waiting.amount) },
            ...(waiting.method_label
              ? [{ label: t("app.renew.methodLine"), value: waiting.method_label }]
              : []),
            {
              label: t("app.renew.sentLine"),
              value: formatDateTime(waiting.created_at, display),
            },
          ]}
          secondary={
            wallet
              ? undefined
              : {
                  label: t("app.renew.withdraw"),
                  busy: withdraw.busy,
                  onPress: () => withdraw.run(waiting.id),
                  testID: "withdraw",
                }
          }
        />
        <ActionStatus action={withdraw} />
      </Screen>
    );
  }

  // The gym's latest answer.
  const answered = mine.data.requests.find(
    (r) => r.status === "approved" || r.status === "rejected",
  );
  const justRenewed =
    answered?.status === "approved" &&
    answered.reviewed_at !== null &&
    Date.parse(answered.reviewed_at) >= openedAt - 60_000 &&
    seen !== answered.id
      ? answered
      : null;

  if (justRenewed) {
    return (
      <Screen onRefresh={refresh}>
        <StatusPanel
          tone="done"
          title={t("app.renew.renewed")}
          lines={[
            { label: t("app.renew.planLine"), value: justRenewed.plan_name ?? "" },
            ...(state.valid_until
              ? [
                  {
                    label: t("app.renew.untilLine"),
                    value: formatDate(state.valid_until, display),
                  },
                ]
              : []),
            { label: t("app.renew.amountLine"), value: formatRs(justRenewed.amount) },
          ]}
          primary={{
            label: t("app.renew.showQr"),
            onPress: () => {
              setSeen(justRenewed.id);
              setStarted(null);
              clear();
              router.navigate("/home");
            },
          }}
          secondary={{
            label: t("app.renew.done"),
            onPress: () => {
              setSeen(justRenewed.id);
              setStarted(null);
              clear();
            },
          }}
        />
      </Screen>
    );
  }

  // --- choosing and paying --------------------------------------------------------

  const { plans, payment_methods: methods } = options.data;
  const method = methods.find((m) => m.id === methodId);
  const online = Boolean(method?.online) && !byHand;
  const wallet = method ? t(`account.${method.kind}` as MessageKey) : "";
  const best = bestValue(plans);
  const rejected = answered?.status === "rejected" ? answered : null;
  const notPaid =
    outcome && (outcome.status === "failed" || outcome.status === "expired");
  const testPaid = outcome?.status === "paid" && outcome.test;

  let next: React.ReactNode;
  if (!plan) {
    next = (
      <Button label={t("app.renew.chooseFirst")} disabled onPress={() => undefined} />
    );
  } else if (!method) {
    next = (
      <Button label={t("app.renew.chooseMethod")} disabled onPress={() => undefined} />
    );
  } else if (online) {
    next = (
      <Button
        testID="pay-online"
        label={t("app.renew.payWithShort", { wallet })}
        busy={payOnline.busy}
        onPress={() =>
          payOnline.run({ plan_id: plan.id, payment_method_id: method.id }, wallet)
        }
      />
    );
  } else {
    next = (
      <Button
        testID="ive-paid"
        label={t("app.renew.sent")}
        busy={send.busy}
        onPress={() => {
          // A transaction ID or a screenshot, before anything is sent.
          if (!ref.trim() && !screenshot) {
            setNeedProof(true);
            scrollTo(where.current.finish);
            return;
          }
          send.run({
            plan_id: plan.id,
            payment_method_id: methodId,
            amount: total,
            transaction_ref: ref.trim() || null,
          });
        }}
      />
    );
  }

  return (
    <Screen
      onRefresh={refresh}
      scrollRef={scroll}
      footer={
        <CheckoutBar
          total={plan ? total : null}
          caption={plan ? plan.name : t("app.renew.total")}
        >
          {next}
        </CheckoutBar>
      }
    >
      <Title>{t("app.renew.title")}</Title>

      {/* Where they stand, and when the new one would start. */}
      <Card style={{ gap: space(3) }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: space(3) }}>
          <View style={{ flex: 1, gap: space(1) }}>
            <Label>{t("app.renew.now")}</Label>
            <Txt weight="semibold" size={16} color={colors.ink}>
              {state.plan_name ?? t("app.home.status.none")}
            </Txt>
            {state.valid_until ? (
              <Txt size={14} color={colors.muted}>
                {state.status === "expired"
                  ? t("app.renew.endedOn", {
                      date: formatDate(state.valid_until, display),
                    })
                  : t("app.renew.activeUntil", {
                      date: formatDate(state.valid_until, display),
                    })}
              </Txt>
            ) : null}
          </View>
          {state.status === "active" ? (
            <View style={{ alignItems: "center" }}>
              <Txt
                weight="bold"
                size={24}
                color={brand}
                style={{ fontVariant: ["tabular-nums"] }}
              >
                {state.days_left}
              </Txt>
              <Txt size={12} color={colors.faint}>
                {t("app.home.daysLeft")}
              </Txt>
            </View>
          ) : null}
        </View>
        <View style={{ height: 1, backgroundColor: colors.hairline }} />
        <View style={{ flexDirection: "row", alignItems: "center", gap: space(2) }}>
          <Icon name="visits" size={18} color={colors.faint} />
          <Txt size={14} color={colors.muted} style={{ flex: 1 }}>
            {t("app.renew.startsOn", {
              date: formatDate(options.data.renewal_starts_on, display),
            })}
          </Txt>
        </View>
      </Card>

      {rejected ? (
        <Notice tone="warning">
          {t("app.renew.rejected", { reason: rejected.reject_reason ?? "" })}
        </Notice>
      ) : null}
      {notPaid ? <Notice tone="warning">{t("pay.notPaid")}</Notice> : null}
      {testPaid ? (
        <Notice>
          {t("pay.paidTest", {
            wallet: t(`account.${outcome.provider}` as MessageKey),
          })}
        </Notice>
      ) : null}

      <Step n={1} title={t("app.renew.choosePlan")} done={Boolean(plan)}>
        <View style={{ gap: space(2.5) }} accessibilityRole="radiogroup">
          {plans.map((p) => (
            <PlanOption
              key={p.id}
              plan={p}
              selected={plan?.id === p.id}
              monthly={perMonth(p)}
              saved={savings(p, plans)}
              best={p.id === best}
              onPress={() => {
                const first = !plan;
                setPlan(p);
                if (first) scrollTo(where.current.pay);
              }}
            />
          ))}
        </View>
        {plan && (mates.length > 0 || admission > 0) ? (
          <Card style={{ gap: space(2), padding: space(3.5) }}>
            {mates.length > 0 ? (
              <Txt size={14} color={colors.muted}>
                {t("app.renew.forEveryone", {
                  names: mates.map((m) => m.name).join(", "),
                })}
              </Txt>
            ) : null}
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <Txt size={14}>{plan.name}</Txt>
              <Money paisa={plan.price} size={14} />
            </View>
            {admission > 0 ? (
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Txt size={14}>{t("sale.admissionFee")}</Txt>
                <Money paisa={admission} size={14} />
              </View>
            ) : null}
          </Card>
        ) : null}
      </Step>

      <View onLayout={(e) => (where.current.pay = e.nativeEvent.layout.y)}>
        <Step
          n={2}
          title={t("app.renew.howToPay")}
          done={Boolean(method)}
          reached={Boolean(plan)}
        >
          {plan ? (
            methods.length === 0 ? (
              <Notice>{t("app.renew.noMethods")}</Notice>
            ) : (
              <View style={{ gap: space(2.5) }} accessibilityRole="radiogroup">
                {methods.map((m) => (
                  <MethodOption
                    key={m.id}
                    method={m}
                    selected={methodId === m.id}
                    onPress={() => {
                      const first = !methodId;
                      setMethodId(m.id);
                      setByHand(false);
                      setNeedProof(false);
                      if (first) scrollTo(where.current.finish);
                    }}
                  />
                ))}
              </View>
            )
          ) : null}
        </Step>
      </View>

      <View onLayout={(e) => (where.current.finish = e.nativeEvent.layout.y)}>
        <Step
          n={3}
          title={
            online ? t("app.renew.step3Online", { wallet }) : t("app.renew.step3Qr")
          }
          done={false}
          reached={Boolean(method)}
        >
          {method && online ? (
            <Card style={{ gap: space(3) }}>
              <View
                style={{ flexDirection: "row", alignItems: "center", gap: space(3) }}
              >
                <WalletBadge kind={method.kind} size={44} />
                <Txt size={14} color={colors.muted} style={{ flex: 1 }}>
                  {t("app.renew.securePay", { wallet, gym: me.gym.name })}
                </Txt>
              </View>
              <Pressable
                accessibilityRole="button"
                onPress={() => setByHand(true)}
                hitSlop={8}
                style={{ minHeight: 44, justifyContent: "center" }}
              >
                <Txt weight="semibold" size={15} color={brand}>
                  {t("app.renew.orByHand")}
                </Txt>
              </Pressable>
              <ActionStatus action={payOnline} />
            </Card>
          ) : null}

          {method && !online ? (
            <>
              <Card style={{ alignItems: "center", gap: space(3) }}>
                <Txt
                  weight="semibold"
                  size={16}
                  color={colors.ink}
                  style={{ textAlign: "center" }}
                >
                  {t("app.renew.payTitle", {
                    amount: formatRs(total),
                    name: method.account_name ?? me.gym.name,
                  })}
                </Txt>
                {method.qr_image_url ? (
                  <>
                    <View
                      style={{
                        padding: space(3),
                        borderRadius: radius.lg,
                        borderWidth: 1,
                        borderColor: colors.hairline,
                        backgroundColor: "#ffffff",
                      }}
                    >
                      <Image
                        source={{ uri: apiUrl(method.qr_image_url) }}
                        contentFit="contain"
                        accessibilityLabel={method.label}
                        style={{ width: 220, height: 220 }}
                      />
                    </View>
                    <Button
                      variant="secondary"
                      label={t("mobile.renew.saveQr")}
                      busy={savePhoto.busy}
                      onPress={() => savePhoto.run(method.qr_image_url!)}
                      style={{ alignSelf: "stretch" }}
                    />
                    <ActionStatus action={savePhoto} />
                  </>
                ) : null}
                {method.account_number ? (
                  <Txt selectable size={15} weight="medium" color={colors.muted}>
                    {method.account_number}
                  </Txt>
                ) : null}
                <Txt size={13} color={colors.faint} style={{ textAlign: "center" }}>
                  {t("app.renew.qrSteps", { amount: formatRs(total) })}
                </Txt>
              </Card>

              <Card style={{ gap: space(4) }}>
                <Label>{t("app.renew.proof")}</Label>
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
                      style={{
                        flexDirection: "row",
                        alignItems: "center",
                        gap: space(3),
                      }}
                    >
                      <Image
                        source={{ uri: screenshot.uri }}
                        style={{ width: 56, height: 96, borderRadius: radius.sm }}
                      />
                      <Txt size={14} style={{ flex: 1 }}>
                        {t("app.renew.screenshotAdded")}
                      </Txt>
                      <Button
                        variant="ghost"
                        label={t("app.renew.removeScreenshot")}
                        onPress={() => setScreenshot(null)}
                      />
                    </View>
                  ) : (
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel={t("app.renew.pickScreenshot")}
                      onPress={() => choose.run("gallery")}
                      style={{
                        minHeight: 56,
                        borderRadius: radius.md,
                        borderWidth: 1,
                        borderStyle: "dashed",
                        borderColor: "#cbd5e1",
                        flexDirection: "row",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: space(2),
                      }}
                    >
                      <Icon name="image" color={colors.muted} />
                      <Txt color={colors.muted}>{t("app.renew.pickScreenshot")}</Txt>
                    </Pressable>
                  )}
                </View>
                {needProof ? (
                  <Notice tone="error">{t("app.renew.needProof")}</Notice>
                ) : null}
                <ActionStatus action={send} />
              </Card>
            </>
          ) : null}
        </Step>
      </View>
    </Screen>
  );
}
