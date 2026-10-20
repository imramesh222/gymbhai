#!/usr/bin/env node
// A gym's own app (PLAN.md §20.3): turn the build file from /admin → Gym
// apps → Build file into brands/<address>/, which app.config.ts reads with
// BRAND=<address>.
//
//   node scripts/brand.mjs ~/Downloads/fitness-zone-build.json
//
// Writes brands/<address>/brand.json and brands/<address>/icon.png (the
// gym's 1024 × 1024 icon, fetched while its link lasts: an hour). The
// brand's google-services.json, from its Android app in Firebase, goes
// beside them by hand (docs/BRANDED_APPS.md).
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const file = process.argv[2];
if (!file) {
  console.error("usage: node scripts/brand.mjs <build file from /admin>");
  process.exit(2);
}

const build = JSON.parse(await readFile(file, "utf8"));
for (const name of [
  "gym",
  "name",
  "color",
  "android_package",
  "ios_bundle_id",
  "scheme",
]) {
  if (!build[name]) {
    console.error(`The build file has no ${name}.`);
    process.exit(1);
  }
}
if (!build.expo_project_id) {
  console.error(
    "The build file has no expo_project_id: create the Expo project, put its id in /admin, and download the build file again.",
  );
  process.exit(1);
}

const dir = join(dirname(fileURLToPath(import.meta.url)), "..", "brands", build.gym);
await mkdir(dir, { recursive: true });

if (build.icon_url) {
  const url = build.icon_url.startsWith("/")
    ? build.api_url + build.icon_url
    : build.icon_url;
  const response = await fetch(url);
  if (!response.ok) {
    console.error(
      `The icon didn't download (${response.status}): get a fresh build file.`,
    );
    process.exit(1);
  }
  await writeFile(join(dir, "icon.png"), Buffer.from(await response.arrayBuffer()));
} else {
  console.error("The gym hasn't sent its icon yet: Settings → Your own app.");
  process.exit(1);
}

const brand = {
  gym: build.gym,
  name: build.name,
  color: build.color,
  android_package: build.android_package,
  ios_bundle_id: build.ios_bundle_id,
  scheme: build.scheme,
  expo_project_id: build.expo_project_id,
};
await writeFile(join(dir, "brand.json"), JSON.stringify(brand, null, 2) + "\n");
console.log(`brands/${build.gym}/ ready. Build it with:`);
console.log(`  BRAND=${build.gym} npx eas-cli build -p android --profile branded`);
