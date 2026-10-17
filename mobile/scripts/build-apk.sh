#!/usr/bin/env bash
# A test .apk of the member app for Android testers (PLAN.md §17.7, 12.9).
#
#   npm run build:apk          (or `make apk` at the repo root)
#
# Built on this Mac, free: no Expo account or Play Store needed. Testers
# install it from a link or a file (README.md, "Android testers").
#
# The API it talks to is fixed at build time: EXPO_PUBLIC_API_URL from
# .env.local (or the environment). A LAN address works for testers on the
# same Wi-Fi; a public HTTPS address for anyone else.
#
# Signed with the debug key: good for sideloading, not for the Play Store.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -f .env.local && -z "${EXPO_PUBLIC_API_URL:-}" ]]; then
  EXPO_PUBLIC_API_URL="$(sed -n 's/^EXPO_PUBLIC_API_URL=//p' .env.local)"
fi
: "${EXPO_PUBLIC_API_URL:?Set EXPO_PUBLIC_API_URL (in .env.local) to the API testers will reach}"
export EXPO_PUBLIC_API_URL NODE_ENV=production
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"

echo "Building against ${EXPO_PUBLIC_API_URL}"
npx expo prebuild --platform android --clean --no-install
# Phones: 64-bit ARM, and 32-bit ARM for the budget phones still common in
# Nepal. The emulator on an Apple-silicon Mac is 64-bit ARM too. (The Play
# Store build later splits these per phone; a test .apk carries both.)
(cd android && ./gradlew assembleRelease -PreactNativeArchitectures=arm64-v8a,armeabi-v7a --quiet)

version="$(node -p 'require("./package.json").version')"
mkdir -p dist
out="dist/gymbhai-${version}-test.apk"
cp android/app/build/outputs/apk/release/app-release.apk "$out"
echo "Done: mobile/$out ($(du -h "$out" | cut -f1))"
