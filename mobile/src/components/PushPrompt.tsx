/**
 * "Get reminders on this phone" on Home after signing in (PLAN.md §17.6),
 * and the on/off setting on Me. The phone asks permission only on the tap.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Linking, Switch, View } from "react-native";

import { t } from "@shared/i18n";

import { keys } from "@/lib/query";
import {
  notNow,
  pushIsOn,
  PushUnavailable,
  shouldOfferPush,
  turnOffPush,
  turnOnPush,
} from "@/lib/push";
import { useSlug } from "@/lib/session";
import { colors, space } from "@/lib/theme";
import { useAction } from "@/lib/useAction";

import { useBrand } from "./brand";
import { Icon } from "./Icon";
import { ActionStatus, Button, Card, LinkButton, Notice, Txt } from "./ui";

function problemText(error: unknown): string | null {
  if (!(error instanceof PushUnavailable)) return null;
  if (error.problem === "blocked") return t("mobile.push.blocked");
  if (error.problem === "not_configured") return t("mobile.push.notConfigured");
  return t("mobile.push.unsupported");
}

export function PushPrompt() {
  const slug = useSlug();
  const brand = useBrand();
  const queryClient = useQueryClient();
  const [show, setShow] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    shouldOfferPush(slug)
      .then(setShow)
      .catch(() => setShow(false));
  }, [slug]);

  const turnOn = useAction(() => turnOnPush(slug), {
    onSuccess: () => {
      setShow(false);
      void queryClient.invalidateQueries({ queryKey: keys.push(slug) });
    },
    onError: (error) => setProblem(problemText(error)),
  });

  if (!show) return null;
  return (
    <Card style={{ gap: space(3) }}>
      <View style={{ flexDirection: "row", gap: space(3), alignItems: "center" }}>
        <Icon name="bell" color={brand} />
        <Txt weight="semibold" style={{ flex: 1 }}>
          {t("app.push.title")}
        </Txt>
      </View>
      <Txt size={14} color={colors.muted}>
        {t("app.push.why")}
      </Txt>
      {problem ? (
        <Notice tone="warning">{problem}</Notice>
      ) : (
        <ActionStatus action={turnOn} />
      )}
      <View style={{ flexDirection: "row", gap: space(3), alignItems: "center" }}>
        <Button
          label={t("app.push.turnOn")}
          busy={turnOn.busy}
          onPress={() => turnOn.run()}
          style={{ flex: 1 }}
        />
        <LinkButton
          label={t("app.push.notNow")}
          color={colors.faint}
          onPress={() => {
            setShow(false);
            void notNow(slug);
          }}
        />
      </View>
    </Card>
  );
}

/** Me → "Reminders on this phone": on or off. */
export function PushSetting() {
  const slug = useSlug();
  const brand = useBrand();
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: keys.push(slug), queryFn: () => pushIsOn(slug) });
  const [problem, setProblem] = useState<unknown>(null);

  const change = useAction(
    (_key: string, on: boolean) => (on ? turnOnPush(slug) : turnOffPush(slug)),
    {
      onSuccess: () => {
        setProblem(null);
        void queryClient.invalidateQueries({ queryKey: keys.push(slug) });
      },
      onError: setProblem,
    },
  );
  const on = Boolean(status.data);
  const text = problemText(problem);

  return (
    <Card style={{ gap: space(2) }}>
      <View
        style={{
          flexDirection: "row",
          alignItems: "center",
          gap: space(3),
          minHeight: 44,
        }}
      >
        <Txt weight="semibold" style={{ flex: 1 }}>
          {t("app.push.setting")}
        </Txt>
        <Switch
          accessibilityLabel={t("app.push.setting")}
          value={on}
          disabled={change.busy || status.isLoading}
          onValueChange={(next) => change.run(next)}
          trackColor={{ true: brand }}
        />
      </View>
      <Txt size={14} color={colors.muted}>
        {on ? t("app.push.isOn") : t("app.push.isOff")}
      </Txt>
      {text ? (
        <View style={{ gap: space(1) }}>
          <Notice tone="warning">{text}</Notice>
          {problem instanceof PushUnavailable && problem.problem === "blocked" ? (
            <LinkButton
              label={t("mobile.openSettings")}
              onPress={() => void Linking.openSettings()}
            />
          ) : null}
        </View>
      ) : (
        <ActionStatus action={change} />
      )}
    </Card>
  );
}
