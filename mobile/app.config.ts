import type { ConfigContext, ExpoConfig } from "expo/config";

/**
 * The GymBhai member app (PLAN.md §17). One app for every gym: the member
 * chooses their gym and the app takes on its name, logo and colour.
 *
 * EXPO_PUBLIC_API_URL is the API it talks to: the production domain by
 * default, the Mac's LAN address in development (see README.md).
 */
const DOMAIN = "app.gymbhai.com";

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: "GymBhai",
  slug: "gymbhai",
  version: "1.0.0",
  orientation: "portrait",
  icon: "./assets/icon.png",
  userInterfaceStyle: "light",
  // gymbhai://<gym> from the welcome SMS; https links once published.
  scheme: "gymbhai",
  ios: {
    bundleIdentifier: "com.gymbhai.member",
    supportsTablet: false,
    associatedDomains: [`applinks:${DOMAIN}`],
    infoPlist: {
      // Development talks to the Mac over plain HTTP on the LAN.
      NSAppTransportSecurity: { NSAllowsLocalNetworking: true },
    },
  },
  android: {
    package: "com.gymbhai.member",
    adaptiveIcon: {
      backgroundColor: "#E6F4FE",
      foregroundImage: "./assets/android-icon-foreground.png",
      backgroundImage: "./assets/android-icon-background.png",
      monochromeImage: "./assets/android-icon-monochrome.png",
    },
    predictiveBackGestureEnabled: false,
    intentFilters: [
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
        backgroundColor: "#ffffff",
        image: "./assets/splash-icon.png",
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
    ["expo-notifications", { color: "#1d5fd1" }],
  ],
  experiments: { typedRoutes: true },
  // Push needs the Expo project's id (`npx eas-cli init`; README.md).
  extra: process.env.EAS_PROJECT_ID
    ? { eas: { projectId: process.env.EAS_PROJECT_ID } }
    : {},
});
