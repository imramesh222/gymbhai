/**
 * Choose your gym (PLAN.md §17.5): scan its poster's QR, type its address,
 * or pick one this phone has opened before.
 */
import { router } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, View } from "react-native";

import { t } from "@shared/i18n";

import { GymLogo, LanguageSwitch } from "@/components/GymParts";
import { Icon } from "@/components/Icon";
import { Screen } from "@/components/Screen";
import { ActionStatus, Button, Card, Field, Label, Title, Txt } from "@/components/ui";
import { ApiError, NetworkError } from "@/lib/api";
import { BRAND_GYM, DEFAULT_BRAND } from "@/lib/config";
import { parseGymLink } from "@/lib/gymLink";
import { memberApi } from "@/lib/memberApi";
import { useSession, type SavedGym } from "@/lib/session";
import { colors, radius, space } from "@/lib/theme";
import { useAction } from "@/lib/useAction";

export default function ChooseGym() {
  const { gyms, openGym } = useSession();
  const [address, setAddress] = useState("");
  const [notFound, setNotFound] = useState(false);

  const find = useAction(
    async (_key: string, text: string) => {
      const link = parseGymLink(text);
      if (!link) throw new ApiError(404, "not_found", "");
      return memberApi.gym(link.slug);
    },
    {
      onSuccess: (gym) => void openGym(gym),
      onError: (error) =>
        setNotFound(error instanceof ApiError && error.status === 404),
    },
  );

  // A gym this phone has opened: fresh details if there's signal, else as
  // saved (signing in needs signal anyway, but a signed-in member's QR not).
  const reopen = useAction(
    async (_key: string, gym: SavedGym) => {
      try {
        return await memberApi.gym(gym.slug);
      } catch (error) {
        if (error instanceof NetworkError) return gym;
        throw error;
      }
    },
    { onSuccess: (gym) => void openGym(gym), offline: "run" },
  );

  // A gym's own app (§20.3) opens its gym by itself; there's nothing to choose.
  useEffect(() => {
    if (BRAND_GYM) find.run(BRAND_GYM);
    // Once, on opening.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (BRAND_GYM)
    return (
      <Screen topInset>
        <View style={{ alignItems: "center", gap: space(3), marginTop: space(16) }}>
          <ActionStatus action={find} />
          <Button
            label={t("common.tryAgain")}
            busy={find.busy}
            onPress={() => find.run(BRAND_GYM!)}
          />
        </View>
      </Screen>
    );

  return (
    <Screen topInset>
      <View style={{ alignItems: "center", gap: space(2), marginTop: space(6) }}>
        <View
          style={{
            width: 64,
            height: 64,
            borderRadius: 20,
            backgroundColor: DEFAULT_BRAND,
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Txt weight="bold" size={30} color="#ffffff">
            G
          </Txt>
        </View>
        <Title style={{ textAlign: "center" }}>{t("mobile.chooseGym.title")}</Title>
        <Txt color={colors.muted} style={{ textAlign: "center" }}>
          {t("mobile.chooseGym.help")}
        </Txt>
      </View>

      {gyms.length > 0 && (
        <Card style={{ gap: space(2) }}>
          <Label>{t("mobile.chooseGym.yours")}</Label>
          {gyms.map((gym) => (
            <Pressable
              key={gym.slug}
              accessibilityRole="button"
              accessibilityLabel={gym.name}
              onPress={() => reopen.run(gym)}
              style={{
                minHeight: 56,
                flexDirection: "row",
                alignItems: "center",
                gap: space(3),
                paddingVertical: space(1),
              }}
            >
              <GymLogo name={gym.name} logoUrl={gym.logo_url} size={40} />
              <Txt weight="semibold" style={{ flex: 1 }}>
                {gym.name}
              </Txt>
              <Icon name="chevron" color={colors.faint} />
            </Pressable>
          ))}
        </Card>
      )}

      <Pressable
        accessibilityRole="button"
        accessibilityLabel={t("mobile.chooseGym.scan")}
        onPress={() => router.push("/scan")}
        style={({ pressed }) => ({
          minHeight: 64,
          borderRadius: radius.lg,
          backgroundColor: DEFAULT_BRAND,
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "center",
          gap: space(3),
          opacity: pressed ? 0.85 : 1,
        })}
      >
        <Icon name="scan" color="#ffffff" />
        <Txt weight="semibold" color="#ffffff">
          {t("mobile.chooseGym.scan")}
        </Txt>
      </Pressable>

      <Card style={{ gap: space(3) }}>
        <Field
          label={t("mobile.chooseGym.address")}
          help={t("mobile.chooseGym.addressHelp")}
          value={address}
          onChangeText={(value) => {
            setAddress(value);
            setNotFound(false);
            find.clearError();
          }}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          returnKeyType="go"
          onSubmitEditing={() => find.run(address)}
          placeholder="fitness-zone"
          testID="gym-address"
        />
        {notFound ? (
          <ActionStatus action={{ waiting: false, error: t("app.noSuchGym") }} />
        ) : (
          <ActionStatus action={find} />
        )}
        <Button
          label={t("mobile.chooseGym.open")}
          busy={find.busy}
          disabled={!address.trim()}
          onPress={() => find.run(address)}
          testID="open-gym"
        />
      </Card>

      <LanguageSwitch />
    </Screen>
  );
}
