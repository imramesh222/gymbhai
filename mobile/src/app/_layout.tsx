/**
 * The GymBhai member app (PLAN.md §17). Three places, each guarded:
 * choosing a gym, signing in to it, and the app itself.
 */
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { useFonts } from "expo-font";
import { Stack, useSegments } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { restoreClock } from "@/lib/clock";
import { LocaleProvider } from "@/lib/locale";
import { startWatchingNetwork } from "@/lib/online";
import { NotificationTaps, setUpNotifications } from "@/lib/push";
import { CACHE_MAX_AGE, CACHE_VERSION, persister, queryClient } from "@/lib/query";
import { SessionProvider, useSession } from "@/lib/session";
import { colors, FONTS } from "@/lib/theme";

/** Guards that fail send people here, and it sends them on (index.tsx). */
export const unstable_settings = { anchor: "index" };

void SplashScreen.preventAutoHideAsync().catch(() => undefined);
startWatchingNetwork();
void restoreClock();
setUpNotifications();

function Navigator({ fontsReady }: { fontsReady: boolean }) {
  const { ready, gym, signedIn } = useSession();
  const loaded = ready && fontsReady;
  // Light text on the tabs' header in the gym's colour; dark everywhere else,
  // the screens over the tabs (classes, progress, the QR…) included.
  const onTabs = useSegments().some((segment) => segment === "(tabs)");

  useEffect(() => {
    if (loaded) void SplashScreen.hideAsync().catch(() => undefined);
  }, [loaded]);
  if (!loaded) return null;

  return (
    <>
      <StatusBar style={gym && signedIn && onTabs ? "light" : "dark"} />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: colors.canvas },
        }}
      >
        <Stack.Screen name="index" />
        <Stack.Protected guard={!gym}>
          <Stack.Screen name="choose-gym" />
          <Stack.Screen name="scan" options={{ presentation: "fullScreenModal" }} />
        </Stack.Protected>
        <Stack.Protected guard={Boolean(gym) && !signedIn}>
          <Stack.Screen name="sign-in" />
          <Stack.Screen
            name="scan-desk"
            options={{ presentation: "fullScreenModal" }}
          />
          <Stack.Screen name="join" />
        </Stack.Protected>
        <Stack.Protected guard={Boolean(gym) && signedIn}>
          <Stack.Screen name="(app)" />
        </Stack.Protected>
        {/* Links into the app: gymbhai://<gym>, https://app.gymbhai.com/<gym>/... */}
        <Stack.Screen name="[gym]" />
      </Stack>
      {gym && signedIn ? <NotificationTaps /> : null}
    </>
  );
}

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts(FONTS);
  return (
    <SafeAreaProvider>
      <PersistQueryClientProvider
        client={queryClient}
        persistOptions={{ persister, maxAge: CACHE_MAX_AGE, buster: CACHE_VERSION }}
      >
        <SessionProvider>
          <LocaleProvider>
            {/* A font that fails to load falls back to the phone's. */}
            <Navigator fontsReady={fontsLoaded || Boolean(fontError)} />
          </LocaleProvider>
        </SessionProvider>
      </PersistQueryClientProvider>
    </SafeAreaProvider>
  );
}
