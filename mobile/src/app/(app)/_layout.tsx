/** Signed in: the tabs, the screens over them, and live updates. */
import { Stack } from "expo-router";

import { t } from "@shared/i18n";

import { LiveUpdates } from "@/lib/LiveUpdates";
import { colors, fontFamily } from "@/lib/theme";

export default function SignedIn() {
  return (
    <>
      <LiveUpdates />
      <Stack
        screenOptions={{
          headerTintColor: colors.ink,
          headerTitleStyle: { fontFamily: fontFamily("semibold") },
          headerBackButtonDisplayMode: "minimal",
          contentStyle: { backgroundColor: colors.canvas },
        }}
      >
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="notices" options={{ title: t("app.notices") }} />
        <Stack.Screen name="freeze" options={{ title: t("app.freeze.title") }} />
        <Stack.Screen
          name="qr"
          options={{ presentation: "fullScreenModal", headerShown: false }}
        />
      </Stack>
    </>
  );
}
