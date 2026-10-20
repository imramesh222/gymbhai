# The member app: run, test, share with testers

The phone app for members (PLAN.md §17) lives in `mobile/`. This guide covers
running it on the Mac, its automatic tests, building a test `.apk` for Android
testers, and letting iPhone testers try it in Expo Go. Publishing to Google
Play and the App Store comes later (PLAN.md §17.7, "Afterwards").

Starting, stopping and changing Wi-Fi day to day: `docs/LOCAL.md`.

Everything here is free. The accounts involved: the Expo account that owns
the project (`mero-gym`), a shared Expo account for iPhone testers, and later
a free Firebase project for Android notifications.

---

## 1. One-time setup on the Mac

1. The backend running: `make up` at the repo root, with `MASTER_OTP` set in
   `.env` (any 6 digits; members of test gyms sign in with it).
2. The app's packages: `cd mobile && npm install`.
3. Tell the app where the API is: `make mobile-env` writes this Mac's Wi-Fi
   address into `mobile/.env.local` (run it again whenever you change Wi-Fi).
   It also sets `PUBLIC_APP_URL` in `.env` to the same address and restarts the
   API, so the web pages the app opens (a wallet's checkout) load on the phone.
   By hand: find the Mac's Wi-Fi address
   (System Settings → Wi-Fi → Details, or `ipconfig getifaddr en0`), then:
   ```sh
   echo "EXPO_PUBLIC_API_URL=http://192.168.1.20:8001" > mobile/.env.local
   ```
   Use the LAN address, not `localhost`: phones, the Android emulator and the
   iPhone simulator all reach the Mac through it.
4. For the automatic tests: Maestro, `brew install mobile-dev-inc/tap/maestro`.
   Xcode (iPhone simulator) and Android Studio's SDK (emulator) are already on
   this Mac.

## 2. Run it while developing

```sh
cd mobile
npx expo start
```

Press `i` for the iPhone simulator or `a` for the Android emulator; Expo Go is
installed on them automatically. Code changes appear at once.

Sign in to any gym in the dev database. To get a known one:

```sh
make seed-app     # gym "e2e-app" ("App Test Gym"), made fresh each time
```

| Member | Mobile number |
|---|---|
| Ram Test | 9800000101 |
| Hari Test and Gita Test (shared phone: "Who are you?") | 9800000102 |
| Sita, Maya, Bina, Kiran Test | 9800000103 … 106 |

The code is your `MASTER_OTP`. Every member has a paid month ending in 20 days;
the gym has an eSewa account and the join form on.

**On your own Android phone, use a development build** instead of Expo Go:
`make apk-dev` makes `mobile/dist/gymbhai-1.0.0-dev.apk`. Install it once;
it opens the code live from `npx expo start` (scan the QR, or it lists the
Mac's server), has notifications, and never says "incompatible". Rebuild it
only when a native module or permission is added. It replaces the test
`.apk` on the phone (same app ID), and the other way round.

**Expo Go's limits.** It runs everything except notifications on Android
(Expo removed them from Expo Go in SDK 53). The app runs anyway, with "Turn on"
saying this phone can't get notifications. The `.apk` has them.

## 3. The automatic tests

| Command | What it checks | Time |
|---|---|---|
| `make test-mobile` | Jest: one tap is one request, the WebSocket client, the API client (refresh, retries, the server's clock), links, which screens a live event refreshes | seconds |
| `make lint` | Includes the app: ESLint (a rule refuses API calls from a button without `useAction`) and TypeScript | ~1 min |
| `make e2e-mobile` | Maestro: the app on a simulator, as a member uses it | ~6 min |

**Maestro flows** (`mobile/e2e/`): sign in and show the QR; three fast taps on
*I've paid* make one request; every screen opens; *Who are you?* on a shared
phone; Nepali; asking to join; signing out; the QR with no signal.

```sh
# iPhone simulator, in Expo Go (start `npx expo start` in mobile/ first,
# and open the simulator once):
make e2e-mobile

# Android emulator, in Expo Go:
make e2e-mobile app=host.exp.exponent expo_url=exp://10.0.2.2:8081

# The installed .apk on the emulator or a phone (adds the offline flow):
make e2e-mobile app=com.gymbhai.member
```

`make e2e-mobile` makes the test gym fresh first. A failed flow leaves
screenshots and a log under `~/.maestro/tests/<date>/`.

On a new Android emulator, turn off two keyboard extras once: the stylus
tutorial swallows typed text, and the keyboard's spell checker can crash
mid-flow (which looks like the app closing):

```sh
adb shell settings put secure stylus_handwriting_enabled 0
adb shell settings put secure spell_checker_enabled 0
```

## 4. Android testers: the `.apk`

### Build it

```sh
make apk
```

The first build takes 10–15 minutes (Gradle downloads its tools); later ones
are a few minutes. The file appears at `mobile/dist/gymbhai-1.0.0-test.apk`.

The app talks to whatever `EXPO_PUBLIC_API_URL` was when it was built:

- **Testers on your Wi-Fi** (in the same room): your LAN address, as in step 1.
  Keep the Mac awake with `make up` running while they test.
- **Testers anywhere**: a public HTTPS address, i.e. the staging or production
  server (`docs/DEPLOY.md`). Build with
  `EXPO_PUBLIC_API_URL=https://app.gymbhai.com make apk`.

It is signed with a test key: fine to install by hand, not for the Play Store.

### Send it to a tester

Share the file by Google Drive, WhatsApp or Viber (as a document, so it isn't
compressed), or a USB cable. Then tell them:

> 1. Open the file on your phone and tap **Install**.
> 2. If the phone asks, allow your browser / WhatsApp to **install unknown
>    apps** (Settings → Apps → Special access), then tap Install again.
> 3. If Play Protect warns about an unknown developer, tap **More details →
>    Install anyway**. That's because it's a test version, not from Play Store.
> 4. Open **GymBhai**, scan your gym's poster QR or type its address, and sign
>    in with your number.

A new build installs over the old one; the tester stays signed in.

### Install on the emulator or a cabled phone yourself

```sh
~/Library/Android/sdk/platform-tools/adb install -r mobile/dist/gymbhai-1.0.0-test.apk
```

## 5. iPhone testers: Expo Go

An iPhone can't install an app outside the App Store without the paid Apple
account, so iPhone testers use **Expo Go** (free, App Store) to open the app
from your Mac.

Expo Go on an iPhone only opens a project from your Mac if both are signed
in to **the same Expo account**. So that testers never need your own login,
make one shared account just for testing:

1. Create a free account at <https://expo.dev/signup>, for example
   `gymbhai-testers`, with a password you are happy to share with testers.
2. On the Mac: `cd mobile && npx expo login` with that account.
3. Start the app for them: `npx expo start` (same Wi-Fi), or
   `npx expo start --tunnel` for testers elsewhere. The first `--tunnel` asks
   to install a small package; say yes.
4. Send the tester these steps, with the QR code that `npx expo start` prints
   (a screenshot of the terminal is fine):

> 1. Install **Expo Go** from the App Store.
> 2. Open Expo Go, tap the account icon (top right) and sign in as
>    `gymbhai-testers` with the password we sent you.
> 3. Open the iPhone **Camera** and point it at the QR code. Tap the banner
>    that appears: GymBhai opens inside Expo Go.
> 4. Choose your gym and sign in with your number.
> 5. Next time, open Expo Go: GymBhai is under **Recently opened**.

What to know:

- It works only while your Mac is running `npx expo start`.
- The phone must reach the API too. On the same Wi-Fi, the LAN address in
  `mobile/.env.local` works. With `--tunnel`, the tester is elsewhere, so the
  API has to be public: set `EXPO_PUBLIC_API_URL` to the staging server.
- Notifications aren't tested on iPhones before publishing (PLAN.md §17.6):
  they need Apple's push key, which comes with the paid Apple account.
- Expo Go on the App Store runs only the newest Expo SDK. The app uses SDK 58;
  when Expo releases SDK 59, upgrade the app (`npx expo install expo@^59
  --fix`) or Expo Go stops opening it.

## 6. Notifications (when you are ready to test them)

The Expo project is set up: `@mero-gym/mero-gym`, its ID in
`mobile/app.config.ts`. What's left is Android's push service, Firebase
(free), done once:

1. <https://console.firebase.google.com> → **Add project** (any name, e.g.
   GymBhai; Analytics not needed).
2. In it: **Add app → Android**, package name `com.gymbhai.member`. Download
   `google-services.json` and put it at `mobile/google-services.json`. The
   app config picks it up by itself.
3. Firebase → ⚙ **Project settings → Service accounts → Generate new private
   key**. That downloads a JSON key: it lets Expo send through your Firebase.
   Keep it out of the repo.
4. Give that key to Expo, from `mobile/`:
   `npx eas-cli credentials -p android` → choose a build profile if asked →
   **Google Service Account** → **Manage your Google Service Account Key for
   Push Notifications (FCM V1)** → **Upload** → pick the JSON from step 3.
5. `make apk`, install it on a real Android phone (an emulator with Play
   Store images works too), sign in, Home → **Turn on**, allow notifications.
6. From the staff dashboard, publish a notice with *Also send to their
   phones*. It arrives as a notification; tapping it opens Notices. The
   notice says *Notification to 1*.

The server needs nothing more: it sends to the app through Expo with the same
rules as the web app's push (`EXPO_ACCESS_TOKEN` in `.env` only if you turn
on Expo's "enhanced push security" for the project). In development the
server only logs pushes unless `PUSH_PROVIDER=webpush` is set in `.env`
(which also needs `VAPID_PRIVATE_KEY`, from `make vapid`).

iPhone push needs Apple's push key, which comes with the paid Apple account:
tested at publishing time.

## 7. Cloud builds and updates (EAS)

Expo's servers can build the app (no Android SDK needed, iPhone builds
possible) and send new JavaScript to installed apps without a new `.apk`.
The project is `@mero-gym/mero-gym`; profiles are in `mobile/eas.json`.
Expo's free plan allows a limited number of builds and update users each
month (see expo.dev/pricing); local builds (`make apk`) cost nothing.

Once: `npm install -g eas-cli`, then `eas login`, and run everything from `mobile/`.

| Profile | What it makes | Talks to |
|---|---|---|
| `development` | A development build `.apk` (like `make apk-dev`): loads code live from `npx expo start` | your Mac's dev server |
| `preview` | A test `.apk` for testers (like `make apk`), with a download link from Expo | `https://app.gymbhai.com` |
| `production` | The Play Store bundle (`.aab`) / App Store build | `https://app.gymbhai.com` |

`preview` and `production` point at the real domain: use them once the
server is deployed (`docs/DEPLOY.md`). Before that, use `make apk` or the
`development` profile.

**Builds**

```sh
eas build -p android --profile development   # dev build .apk, link to install
eas build -p android --profile preview       # tester .apk, link to share
eas build -p android --profile production    # Play Store .aab (when publishing)
eas build -p ios --profile production        # needs the paid Apple account
eas build:list                               # your builds and their links
```

The build prints a link (and a QR) to the `.apk` on expo.dev: send that to
testers instead of the file. The first Android build asks to generate a
signing key on Expo's servers: say yes, and keep using it.

**Updates** (new JavaScript, no reinstall)

```sh
eas update --channel preview --message "Fix renew screen"
eas update --channel production --message "..."   # after publishing
eas update:list                                   # what was sent
eas update:republish --group <id>                 # roll back to an earlier one
```

An installed app on that channel picks the update up the next time it opens
(and uses it the time after). It only works for builds from `eas build` with
the same `version` in `app.config.ts`: a change in native code (a new Expo
module, a permission, the icon) needs a new build, and then bump `version`.
Updates use `EXPO_PUBLIC_API_URL` from your shell or `.env.local` when you run
the command, so for `preview` run
`EXPO_PUBLIC_API_URL=https://app.gymbhai.com eas update --channel preview ...`.

## 8. When something goes wrong

| Symptom | Fix |
|---|---|
| "Can't reach GymBhai" on every screen | The phone can't reach `EXPO_PUBLIC_API_URL`: same Wi-Fi? `make up` running? Try the address in the phone's browser: `http://<ip>:8001/health` should say ok. |
| Code never arrives | In development no SMS is sent: use `MASTER_OTP`. |
| "Too many codes asked for" | At most three codes per number in 15 minutes, counted by number (a fresh `make seed-app` doesn't reset it): wait, or sign in as another test member. |
| Expo Go: "Project is incompatible", *requires a newer version* | The store's Expo Go is behind the app's SDK (the Play Store can lag weeks after a release). Android: install the test `.apk` instead, or Expo's own Expo Go for SDK 58 (`https://github.com/expo/expo-go-releases/releases`, `Expo-Go-58.0.4.apk`), or plug the phone in and press `a` in `npx expo start`, which installs the right one. |
| Expo Go: "Project is incompatible", *requires an older version* | Expo Go moved on to a newer SDK: upgrade the app (`npx expo install expo@^59 --fix`). |
| iPhone: "You need to be signed in to Expo Go and Expo CLI" | Section 5: same Expo account on both. |
| Android build fails with SDK not found | `export ANDROID_HOME=~/Library/Android/sdk` |
| A Maestro flow fails | Screenshots and a log in `~/.maestro/tests/<date>/`; rerun the one flow: `cd mobile && maestro test e2e/02-renew-once.yaml -e APP_ID=... -e CODE=...` |
