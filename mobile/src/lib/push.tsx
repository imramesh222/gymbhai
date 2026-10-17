/**
 * Notifications on this phone (PLAN.md §17.6).
 *
 * - Asked for only when the member taps "Turn on", never on launch.
 * - The Expo push token is registered as an `expo` subscription for the open
 *   gym; the server then sends reminders, notices and answers here instead
 *   of by SMS (the same rules as the web app's push, M8).
 * - Signing out turns this phone's off first: on a shared phone the next
 *   member must not get this one's reminders.
 * - Tapping one opens the screen it's about.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import { isRunningInExpoGo } from "expo";
import Constants from "expo-constants";
import { router } from "expo-router";
import { useEffect } from "react";
import { Platform } from "react-native";

import { memberApi } from "./memberApi";
import { useSession } from "./session";

const tokenKey = (slug: string) => `gymbhai.push.${slug}`;
const askedKey = (slug: string) => `gymbhai.pushAsked.${slug}`;

export type PushProblem = "unsupported" | "blocked" | "not_configured";

export class PushUnavailable extends Error {
  constructor(readonly problem: PushProblem) {
    super(problem);
  }
}

/**
 * Expo Go on Android has no push since SDK 53 and crashes on loading the
 * module; development builds and the .apk have it. Loaded only where it is.
 */
type NotificationsModule = typeof import("expo-notifications");
const Notifications: NotificationsModule | null =
  Platform.OS === "android" && isRunningInExpoGo()
    ? null
    : // Conditional on purpose: an import would load it everywhere.
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      require("expo-notifications");

/** How notifications look while the app is open: shown, like any other. */
export function setUpNotifications() {
  if (!Notifications) return;
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });
  if (Platform.OS === "android") {
    void Notifications.setNotificationChannelAsync("default", {
      name: "GymBhai",
      importance: Notifications.AndroidImportance.HIGH,
    }).catch(() => undefined);
  }
}

function projectId(): string | undefined {
  return (
    (Constants.expoConfig?.extra?.eas?.projectId as string | undefined) ??
    Constants.easConfig?.projectId
  );
}

/** This phone's Expo push token, asking permission if need be. */
async function expoToken(ask: boolean): Promise<string> {
  if (!Notifications) throw new PushUnavailable("unsupported");
  let { status } = await Notifications.getPermissionsAsync();
  if (status !== "granted" && ask) {
    status = (await Notifications.requestPermissionsAsync()).status;
  }
  if (status !== "granted") throw new PushUnavailable("blocked");
  const id = projectId();
  if (!id) throw new PushUnavailable("not_configured");
  try {
    return (await Notifications.getExpoPushTokenAsync({ projectId: id })).data;
  } catch {
    // An emulator without Google Play services, or no push service at all.
    throw new PushUnavailable("unsupported");
  }
}

/** "Turn on": permission, token, and the server told. */
export async function turnOnPush(slug: string): Promise<void> {
  const token = await expoToken(true);
  await memberApi.pushOn(token);
  await AsyncStorage.setItem(tokenKey(slug), token);
}

export async function turnOffPush(slug: string): Promise<void> {
  const token = await AsyncStorage.getItem(tokenKey(slug));
  if (token) await memberApi.pushOff(token);
  await AsyncStorage.removeItem(tokenKey(slug));
}

/** On for this gym on this phone, as far as the server knows. */
export async function pushIsOn(slug: string): Promise<boolean> {
  const token = await AsyncStorage.getItem(tokenKey(slug));
  if (!token) return false;
  return (await memberApi.pushStatus(token)).subscribed;
}

/** Whether to offer "Get reminders on this phone" on Home. */
export async function shouldOfferPush(slug: string): Promise<boolean> {
  const [token, asked] = await Promise.all([
    AsyncStorage.getItem(tokenKey(slug)),
    AsyncStorage.getItem(askedKey(slug)),
  ]);
  return !token && !asked;
}

export async function notNow(slug: string): Promise<void> {
  await AsyncStorage.setItem(askedKey(slug), "1");
}

/**
 * Where a notification's link goes. The server writes web paths
 * ("/<gym>/renew"); the app's screens have the same names.
 */
export function screenFor(url: unknown, slug: string): string | null {
  if (typeof url !== "string" || !url.startsWith("/")) return null;
  const [gymPart, screen = ""] = url.slice(1).split(/[/?#]/);
  if (gymPart !== slug) return `/${url.slice(1)}`; // another gym: the link route opens it
  const known = ["", "renew", "payments", "visits", "notices", "freeze", "profile"];
  if (!known.includes(screen) || screen === "") return "/home";
  return `/${screen === "profile" ? "me" : screen}`;
}

/**
 * Taps on notifications, while signed in: open the screen, and before the
 * app's first render, the one that launched it.
 */
export function NotificationTaps() {
  const { gym, setBeforeSignOut } = useSession();
  const slug = gym?.slug;

  useEffect(() => {
    if (!slug) return;
    setBeforeSignOut(() => turnOffPush(slug));
    return () => setBeforeSignOut(null);
  }, [slug, setBeforeSignOut]);

  return Notifications && slug ? (
    <OpenTapped notifications={Notifications} slug={slug} />
  ) : null;
}

function OpenTapped({
  notifications,
  slug,
}: {
  notifications: NotificationsModule;
  slug: string;
}) {
  const last = notifications.useLastNotificationResponse();
  useEffect(() => {
    if (!last) return;
    if (last.actionIdentifier !== notifications.DEFAULT_ACTION_IDENTIFIER) return;
    const target = screenFor(last.notification.request.content.data?.url, slug);
    notifications.clearLastNotificationResponse();
    if (target) router.navigate(target as never);
  }, [last, slug, notifications]);
  return null;
}
