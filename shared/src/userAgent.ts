/**
 * "Chrome on Android" from a browser's User-Agent, for My account → Devices
 * and a member's signed-in devices (PLAN.md §17.5). Good enough to tell a desk
 * PC from a phone; it never decides anything. The phone app sends
 * "GymBhai/<version> (Android 14)" (mobile/src/lib/api.ts).
 */
const BROWSERS: [RegExp, string][] = [
  [/GymBhai\//, "GymBhai app"],
  [/EdgA?\//, "Edge"],
  [/SamsungBrowser\//, "Samsung Internet"],
  [/OPR\/|Opera/, "Opera"],
  [/Firefox\/|FxiOS\//, "Firefox"],
  [/CriOS\/|Chrome\//, "Chrome"],
  [/Safari\//, "Safari"],
];

const SYSTEMS: [RegExp, string][] = [
  [/Android/, "Android"],
  [/iPhone/, "iPhone"],
  [/iPad/, "iPad"],
  [/CrOS/, "ChromeOS"],
  [/Windows/, "Windows"],
  [/Mac OS X|Macintosh/, "Mac"],
  [/Linux/, "Linux"],
];

export function describeDevice(userAgent: string | null): {
  browser: string | null;
  system: string | null;
} {
  const ua = userAgent ?? "";
  const find = (list: [RegExp, string][]) =>
    list.find(([pattern]) => pattern.test(ua))?.[1] ?? null;
  return { browser: find(BROWSERS), system: find(SYSTEMS) };
}
