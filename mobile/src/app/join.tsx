/**
 * "Not a member yet? Ask to join" (PLAN.md §16.4, 9.5): the gym gets an
 * enquiry to call back. Nobody becomes a member from here.
 */
import { useQuery } from "@tanstack/react-query";
import { router } from "expo-router";
import { useState } from "react";
import { Pressable, View } from "react-native";

import { t, type MessageKey } from "@shared/i18n";
import { formatRs } from "@shared/money";
import { LEAD_SOURCES, type LeadSource } from "@shared/types";

import { useBrand } from "@/components/brand";
import { Screen } from "@/components/Screen";
import {
  ActionButton,
  Card,
  Field,
  Label,
  LinkButton,
  Notice,
  Spinner,
  Title,
  Txt,
} from "@/components/ui";
import { memberApi } from "@/lib/memberApi";
import { useSession } from "@/lib/session";
import { colors, radius, space, tint } from "@/lib/theme";
import { useAction } from "@/lib/useAction";

function Chip({
  label,
  selected,
  onPress,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  const brand = useBrand();
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ checked: selected }}
      accessibilityLabel={label}
      onPress={onPress}
      style={{
        minHeight: 44,
        paddingHorizontal: space(4),
        borderRadius: 999,
        justifyContent: "center",
        borderWidth: selected ? 2 : 1,
        borderColor: selected ? brand : colors.hairline,
        backgroundColor: selected ? tint(brand, 0.08) : colors.surface,
      }}
    >
      <Txt size={15} weight={selected ? "semibold" : "regular"}>
        {label}
      </Txt>
    </Pressable>
  );
}

export default function Join() {
  const { gym } = useSession();
  const slug = gym?.slug ?? "";
  const options = useQuery({
    queryKey: [slug, "join"],
    queryFn: () => memberApi.joinOptions(slug),
    enabled: Boolean(slug),
    retry: false,
  });
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [planId, setPlanId] = useState<string | null>(null);
  const [source, setSource] = useState<LeadSource>("other");
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);

  const ask = useAction(
    (key: string) =>
      memberApi.askToJoin(
        slug,
        { name, phone, plan_id: planId, source, message: message.trim() || null },
        key,
      ),
    { onSuccess: () => setSent(true) },
  );

  if (!gym) return null;

  return (
    <Screen topInset>
      <Title>{t("app.join.title", { gym: gym.name })}</Title>
      {options.isError ? (
        <Notice>{t("app.join.off")}</Notice>
      ) : sent ? (
        <Notice tone="success">{t("app.join.sent")}</Notice>
      ) : !options.data ? (
        <Spinner />
      ) : (
        <Card style={{ gap: space(4) }}>
          <Txt color={colors.muted}>{t("app.join.help")}</Txt>
          <Field
            label={t("member.name")}
            value={name}
            onChangeText={setName}
            testID="join-name"
            autoComplete="name"
            textContentType="name"
          />
          <Field
            label={t("member.phone")}
            value={phone}
            onChangeText={setPhone}
            testID="join-phone"
            keyboardType="phone-pad"
            autoComplete="tel"
            textContentType="telephoneNumber"
          />
          {options.data.plans.length > 0 && (
            <View style={{ gap: space(2) }}>
              <Label>{t("leads.plan")}</Label>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: space(2) }}>
                <Chip
                  label={t("leads.noPlan")}
                  selected={planId === null}
                  onPress={() => setPlanId(null)}
                />
                {options.data.plans.map((plan) => (
                  <Chip
                    key={plan.id}
                    label={
                      plan.price === null
                        ? plan.name
                        : `${plan.name} — ${formatRs(plan.price)}`
                    }
                    selected={planId === plan.id}
                    onPress={() => setPlanId(plan.id)}
                  />
                ))}
              </View>
            </View>
          )}
          <View style={{ gap: space(2) }}>
            <Label>{t("leads.source")}</Label>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: space(2) }}>
              {LEAD_SOURCES.filter((s) => s !== "walk_in").map((s) => (
                <Chip
                  key={s}
                  label={t(`leads.source.${s}` as MessageKey)}
                  selected={source === s}
                  onPress={() => setSource(s)}
                />
              ))}
            </View>
          </View>
          <Field
            label={t("app.join.message")}
            value={message}
            onChangeText={setMessage}
            multiline
            style={{ borderRadius: radius.md }}
          />
          <ActionButton
            action={ask}
            args={[]}
            label={t("app.join.send")}
            disabled={!name.trim() || !phone.trim()}
            testID="join-send"
          />
        </Card>
      )}
      {/* Opened from a link, there's no screen behind it to go back to. */}
      <LinkButton
        label={t("app.join.member")}
        onPress={() =>
          router.canGoBack() ? router.back() : router.replace("/sign-in")
        }
      />
    </Screen>
  );
}
