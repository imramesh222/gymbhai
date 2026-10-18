#!/usr/bin/env bash
# An .apk of the member app, built on this Mac, free (PLAN.md §17.7, 12.9).
#
#   npm run build:apk        (make apk)      a test build for testers: the
#                                            app's code is inside it
#   npm run build:apk -- dev (make apk-dev)  a development build: loads the
#                                            code live from `npx expo start`
#                                            on this Mac, like Expo Go, but
#                                            with everything Expo Go lacks
#                                            (notifications on Android) and
#                                            never "incompatible"
#
# Both are com.gymbhai.member: installing one replaces the other.
#
# The test build talks to EXPO_PUBLIC_API_URL from .env.local (or the
# environment), fixed at build time: a LAN address for testers on the same
# Wi-Fi, a public HTTPS address for anyone else. The development build gets
# it from the dev server each time, so changing .env.local needs no rebuild.
#
# Signed with the debug key: good for sideloading, not for the Play Store.
set -euo pipefail
cd "$(dirname "$0")/.."

kind="${1:-test}"
if [[ "$kind" != "test" && "$kind" != "dev" ]]; then
  echo "usage: build-apk.sh [test|dev]" >&2
  exit 2
fi

if [[ -f .env.local && -z "${EXPO_PUBLIC_API_URL:-}" ]]; then
  EXPO_PUBLIC_API_URL="$(sed -n 's/^EXPO_PUBLIC_API_URL=//p' .env.local)"
fi
: "${EXPO_PUBLIC_API_URL:?Set EXPO_PUBLIC_API_URL (in .env.local) to the API the app will reach}"
export EXPO_PUBLIC_API_URL
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"

echo "Building the ${kind} .apk against ${EXPO_PUBLIC_API_URL}"
npx expo prebuild --platform android --clean --no-install
# Phones: 64-bit ARM, and 32-bit ARM for the budget phones still common in
# Nepal. The emulator on an Apple-silicon Mac is 64-bit ARM too. (The Play
# Store build later splits these per phone; an .apk carries both.)
abis="-PreactNativeArchitectures=arm64-v8a,armeabi-v7a"
if [[ "$kind" == "dev" ]]; then
  (cd android && ./gradlew assembleDebug "$abis" --quiet)
  built="android/app/build/outputs/apk/debug/app-debug.apk"
else
  (cd android && NODE_ENV=production ./gradlew assembleRelease "$abis" --quiet)
  built="android/app/build/outputs/apk/release/app-release.apk"
fi

version="$(node -p 'require("./package.json").version')"
mkdir -p dist
out="dist/gymbhai-${version}-${kind}.apk"
cp "$built" "$out"
echo "Done: mobile/$out ($(du -h "$out" | cut -f1))"
