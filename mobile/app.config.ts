import { existsSync, readFileSync } from "node:fs";

import type { ConfigContext, ExpoConfig } from "expo/config";

/**
 * The GymBhai member app (PLAN.md §17). One app for every gym: the member
 * chooses their gym and the app takes on its name, logo and colour.
 *
 * With BRAND=<gym address>, a gym's own app instead (§20.3): the same code
 * with that gym's name, icon, colour and store ids from
 * brands/<address>/brand.json (scripts/brand.mjs writes it), and that gym
 * fixed. docs/BRANDED_APPS.md.
 *
 * EXPO_PUBLIC_API_URL is the API it talks to: the production domain by
 * default, the Mac's LAN address in development (see README.md).
 */
const DOMAIN = "app.gymbhai.com";
const EAS_PROJECT_ID = "f1c93320-114b-47df-b684-9870466dbb7e";
const API_URL = process.env.EXPO_PUBLIC_API_URL ?? `https://${DOMAIN}`;

interface Brand {
  gym: string;
  name: string;
  color: string;
  android_package: string;
  ios_bundle_id: string;
  scheme: string;
  expo_project_id: string;
}

function brand(): (Brand & { dir: string }) | null {
  const slug = process.env.BRAND;
  if (!slug) return null;
  const dir = `./brands/${slug}`;
  const file = `${dir}/brand.json`;
  if (!existsSync(file)) throw new Error(`No ${file}: run scripts/brand.mjs first.`);
  const found = JSON.parse(readFileSync(file, "utf8")) as Brand;
  if (!found.expo_project_id) throw new Error(`${file} has no expo_project_id.`);
  return { ...found, dir };
}

const BRAND = brand();
const PROJECT_ID =
  BRAND?.expo_project_id ?? process.env.EAS_PROJECT_ID ?? EAS_PROJECT_ID;
// Firebase's file for push on Android (docs/MOBILE.md §6): each brand has
// its own Android app in the Firebase project, so its own file.
const GOOGLE_SERVICES = BRAND
  ? `${BRAND.dir}/google-services.json`
  : "./google-services.json";

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: BRAND?.name ?? "GymBhai",
  // The project's name on expo.dev; the app's own name and package are below.
  slug: BRAND ? `gb-${BRAND.gym}` : "mero-gym",
  version: "1.0.0",
  orientation: "portrait",
  icon: BRAND ? `${BRAND.dir}/icon.png` : "./assets/icon.png",
  userInterfaceStyle: "light",
  // gymbhai://<gym> from the welcome SMS; https links once published. A
  // gym's own app has a scheme of its own, gb-<address>://.
  scheme: BRAND?.scheme ?? "gymbhai",
  ios: {
    bundleIdentifier: BRAND?.ios_bundle_id ?? "com.gymbhai.member",
    supportsTablet: false,
    // app.gymbhai.com's links open the GymBhai app, not a gym's own.
    ...(BRAND ? {} : { associatedDomains: [`applinks:${DOMAIN}`] }),
    infoPlist: {
      // Development talks to the Mac over plain HTTP on the LAN.
      NSAppTransportSecurity: { NSAllowsLocalNetworking: true },
    },
  },
  android: {
    package: BRAND?.android_package ?? "com.gymbhai.member",
    adaptiveIcon: BRAND
      ? { backgroundColor: BRAND.color, foregroundImage: `${BRAND.dir}/icon.png` }
      : {
          backgroundColor: "#E6F4FE",
          foregroundImage: "./assets/android-icon-foreground.png",
          backgroundImage: "./assets/android-icon-background.png",
          monochromeImage: "./assets/android-icon-monochrome.png",
        },
    predictiveBackGestureEnabled: false,
    ...(existsSync(GOOGLE_SERVICES) ? { googleServicesFile: GOOGLE_SERVICES } : {}),
    intentFilters: BRAND
      ? []
      : [
          {
            action: "VIEW",
            autoVerify: true,
            data: [{ scheme: "https", host: DOMAIN }],
            category: ["BROWSABLE", "DEFAULT"],
          },
        ],
  },
  plugins: [
    "expo-router",
    "expo-secure-store",
    "expo-font",
    "expo-localization",
    "expo-sharing",
    "expo-image",
    [
      "expo-splash-screen",
      {
        backgroundColor: BRAND?.color ?? "#ffffff",
        image: BRAND ? `${BRAND.dir}/icon.png` : "./assets/splash-icon.png",
        imageWidth: 160,
      },
    ],
    [
      "expo-camera",
      {
        cameraPermission: "GymBhai uses the camera to scan your gym's QR code.",
        recordAudioAndroid: false,
      },
    ],
    [
      "expo-image-picker",
      {
        photosPermission: "GymBhai lets you choose a payment screenshot or your photo.",
        cameraPermission: "GymBhai uses the camera to take your photo.",
      },
    ],
    [
      "expo-media-library",
      {
        savePhotosPermission: "GymBhai saves your gym's payment QR to your photos.",
        isAccessMediaLocationEnabled: false,
      },
    ],
    [
      "expo-notifications",
      {
        color: BRAND?.color ?? "#1d5fd1",
        icon: "./assets/android-icon-foreground.png",
      },
    ],
    // A test build that talks to a Mac over plain HTTP on the LAN; a build
    // against the HTTPS domain doesn't allow it.
    [
      "expo-build-properties",
      { android: { usesCleartextTraffic: API_URL.startsWith("http://") } },
    ],
  ],
  experiments: { typedRoutes: true },
  // EAS Update (docs/MOBILE.md §7): new JavaScript reaches installed apps
  // without a new .apk. An update only goes to builds of the same app
  // version, so bump "version" when native code changes.
  runtimeVersion: { policy: "appVersion" },
  updates: { url: `https://u.expo.dev/${PROJECT_ID}` },
  // The Expo project (expo.dev): push tokens and EAS builds belong to it.
  // Not a secret; EAS_PROJECT_ID overrides it for another account's project,
  // and a gym's own app has its own project, in the same account.
  owner: process.env.EAS_OWNER ?? "mero-gym",
  extra: {
    eas: { projectId: PROJECT_ID },
    // The one gym a gym's own app is for (src/lib/config.ts, BRAND_GYM).
    ...(BRAND ? { gym: BRAND.gym } : {}),
  },
});
