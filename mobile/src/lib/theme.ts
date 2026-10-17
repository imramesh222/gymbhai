/**
 * Colours and type, matching the web member app (frontend/src/app/globals.css):
 * slate ink on a cool canvas, the gym's own colour for what's theirs.
 */
import { getLocale } from "@shared/i18n";

export const colors = {
  canvas: "#f4f6fa",
  surface: "#ffffff",
  hairline: "#e3e8ef",
  ink: "#0f172a", // slate-900
  text: "#1e293b", // slate-800
  muted: "#475569", // slate-600
  faint: "#64748b", // slate-500
  track: "#e9eef5",
  amber: "#d97706",
  amberBg: "#fffbeb",
  amberInk: "#92400e",
  red: "#b91c1c",
  redBg: "#fef2f2",
  green: "#047857",
  greenBg: "#ecfdf5",
  quiet: "#10b981",
  normal: "#fbbf24",
  busy: "#ef4444",
};

export const radius = { sm: 10, md: 14, lg: 18, xl: 24 };
export const space = (n: number) => n * 4;

/** The bundled fonts (PLAN.md §17.1), loaded in the root layout. */
export const FONTS = {
  Inter_400Regular: require("@expo-google-fonts/inter/400Regular/Inter_400Regular.ttf"),
  Inter_500Medium: require("@expo-google-fonts/inter/500Medium/Inter_500Medium.ttf"),
  Inter_600SemiBold: require("@expo-google-fonts/inter/600SemiBold/Inter_600SemiBold.ttf"),
  Inter_700Bold: require("@expo-google-fonts/inter/700Bold/Inter_700Bold.ttf"),
  NotoSansDevanagari_400Regular: require("@expo-google-fonts/noto-sans-devanagari/400Regular/NotoSansDevanagari_400Regular.ttf"),
  NotoSansDevanagari_500Medium: require("@expo-google-fonts/noto-sans-devanagari/500Medium/NotoSansDevanagari_500Medium.ttf"),
  NotoSansDevanagari_600SemiBold: require("@expo-google-fonts/noto-sans-devanagari/600SemiBold/NotoSansDevanagari_600SemiBold.ttf"),
  NotoSansDevanagari_700Bold: require("@expo-google-fonts/noto-sans-devanagari/700Bold/NotoSansDevanagari_700Bold.ttf"),
};

export type Weight = "regular" | "medium" | "semibold" | "bold";

const SUFFIX: Record<Weight, string> = {
  regular: "400Regular",
  medium: "500Medium",
  semibold: "600SemiBold",
  bold: "700Bold",
};

/**
 * Nepali in Noto Sans Devanagari (which has Latin letters too); English in
 * Inter. A Devanagari name in English falls back to the phone's own font.
 */
export function fontFamily(weight: Weight = "regular"): string {
  return `${getLocale() === "ne" ? "NotoSansDevanagari" : "Inter"}_${SUFFIX[weight]}`;
}

/** The gym's colour, deepened: for the header gradient's far end. */
export function deepen(hex: string, amount = 0.38): string {
  const match = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!match) return hex;
  const value = parseInt(match[1], 16);
  const mix = (channel: number, target: number) =>
    Math.round(channel + (target - channel) * amount);
  const r = mix((value >> 16) & 255, 0x0b);
  const g = mix((value >> 8) & 255, 0x1e);
  const b = mix(value & 255, 0x42);
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, "0")}`;
}

/** A light tint of the gym's colour, for selected rows. */
export function tint(hex: string, alpha = 0.1): string {
  const match = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!match) return hex;
  const value = parseInt(match[1], 16);
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`;
}
