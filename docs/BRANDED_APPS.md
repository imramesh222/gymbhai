# A gym's own app in the stores

A gym can have its own app in the Play Store and App Store, with its name and
icon, instead of being found inside the GymBhai app (PLAN.md §20.3). It is the
same code as the GymBhai app (`mobile/`), built with `BRAND=<gym address>`:
that gym's name, icon, colour and store ids, and that gym fixed (no "choose
your gym", no "switch gym").

**None has been built yet.** The steps below are how it's meant to go; the
first gym's will show what's missing.

| What | Where |
|---|---|
| The gym asks, with name, colour and icon | Settings → Your own app (`/staff/settings/app`) |
| Prices (setup, monthly) | `/admin` → Our plans and prices → *A gym's own app* |
| Each request, its state and store details | `/admin/apps` |
| The build file → `mobile/brands/<address>/` | `node mobile/scripts/brand.mjs <file>` |
| The brand in the app's config | `mobile/app.config.ts` (`BRAND`), `mobile/src/lib/config.ts` (`BRAND_GYM`) |

## Why the gym publishes it

Apple's App Review Guideline 4.2.6: "Apps created from a commercialized
template or app generation service will be rejected unless they are submitted
directly by the provider of the app's content", and such services "should not
submit apps on behalf of their clients". So:

- **The gym** opens an **Apple Developer** account (US$99 a year; as an
  organisation it needs a D-U-N-S number, which takes a few days) and a
  **Google Play developer** account (US$25 once; Google may ask for an
  organisation's documents and a test with 12 testers for new personal
  accounts).
- It adds us: App Store Connect → Users and Access → our Apple ID as *App
  Manager*; Play Console → Users and permissions → our Google account with
  *Release* rights.
- The GymBhai app itself is the "picker" model Apple allows (one app, the
  member chooses their gym), so it stays as it is.

## Building one

1. **/admin/apps**: the gym's request is *asked*. Check the name (30
   characters), the icon, and the store ids (`np.gymbhai.<address>` to start;
   once built they can't change). Make sure the setup is paid (Subscription,
   *Your own app*), or agreed.
2. **Expo project**: on expo.dev, in the `mero-gym` account, *Create project*
   named `gb-<address>`. Put its id in /admin (*Expo project id*) and set the
   state to *building* (the monthly add-on starts).
3. **Firebase** (push on Android): in the Firebase project `gymbhai-69df8`,
   *Add app* → Android → the package from /admin. Download its
   `google-services.json`. In the Expo project, upload the same FCM V1 key as
   the GymBhai app's (docs/MOBILE.md §6).
4. **Build file**: /admin/apps → *Build file*, then
   ```
   cd mobile
   node scripts/brand.mjs ~/Downloads/<address>-build.json
   cp ~/Downloads/google-services.json brands/<address>/
   ```
   The icon comes with it (its link lasts an hour: download the build file
   again if it's stale). `brands/` is kept out of git.
5. **Build and upload**:
   ```
   BRAND=<address> npx eas-cli build -p android --profile branded
   BRAND=<address> npx eas-cli build -p ios --profile branded
   BRAND=<address> npx eas-cli submit -p android --profile production
   ```
   iOS: EAS asks to sign in with an Apple ID that is on the gym's team.
6. **Store listing**: the gym's name, a short description, screenshots
   (from a phone signed in to the gym), the privacy policy
   (`https://app.gymbhai.com/privacy`), and the data-safety answers (phone
   number, name, photos the member adds; nothing sold or shared).
7. When review starts: *in review*. When it's out: *live*, with the two store
   links. The gym's members then see *Get the <name> app* on their web app's
   Home, and Settings → Your own app shows the links.

## Updates

New JavaScript goes to a brand's installed apps with EAS Update on its own
project: `BRAND=<address> npx eas-cli update --channel production`. A change
to native code (a new Expo SDK, a new permission) needs a new build per brand,
as for the GymBhai app; bump `version` in `app.config.ts`.

## Stopping one

Set it to *stopped* in /admin: the monthly add-on stops and members are no
longer offered it. Unpublishing is the gym's (it's their account); the app
keeps working until they do, as long as the gym is on GymBhai.
