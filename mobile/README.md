# GymBhai member app (React Native, Expo)

The phone app for members (PLAN.md §17): choose your gym, sign in with a code,
show the door QR (offline too), renew and pay the gym, see payments, visits and
notices, ask to freeze, get notifications. Staff keep the web dashboard.

- Expo SDK 58, Expo Router (`src/app/`), TypeScript.
- Strings, the member QR, dates, money and the API types come from
  `../shared/src` (imported as `@shared/...`), the same code the web app uses.
- Talks to the API directly: REST, plus one WebSocket for live updates
  (`src/lib/live.ts`, server: `backend/app/api/routes/member_socket.py`).

## Run it in development

The API must be running (`make up` at the repo root). Point the app at it with
the Mac's LAN address, so a simulator, an emulator and a real phone on the
same Wi-Fi all reach it:

```sh
cd mobile
npm install
echo "EXPO_PUBLIC_API_URL=http://192.168.1.20:8001" > .env.local   # your Mac's IP
npx expo start
```

Then press `i` (iOS simulator), `a` (Android emulator), or scan the QR with
**Expo Go** on a phone. Sign in to a gym from the dev database; with
`MASTER_OTP` set in the root `.env`, that code works for every member.

Expo Go has everything except push notifications on Android (removed from
Expo Go in SDK 53): the app runs there with notifications turned off. A
development build has them all: `npx expo run:android` / `npx expo run:ios`.

## Checks

```sh
npm run typecheck
npm run lint        # includes the rule: API calls from a button go through useAction
npm test            # Jest: double taps, the socket, the API client, links
npx expo-doctor     # dependency versions match the SDK
make e2e-mobile     # (repo root) Maestro flows on a simulator: e2e/README.md
```

## Testers

`make apk` builds a test `.apk` for Android testers; iPhone testers use Expo
Go. How to build, send and install, step by step: `docs/MOBILE.md`.

## Notifications

Push goes through Expo's service, for the Expo project `@mero-gym/mero-gym`
(its ID is in `app.config.ts`). Android also needs Firebase's
`google-services.json` here and its key uploaded to Expo: `docs/MOBILE.md` §6.
Until then, "Turn on" says this phone can't get notifications; everything
else works, and the gym reaches the member by SMS.

## How it fits together

| Where | What |
|---|---|
| `src/lib/api.ts` | Requests, the session (refresh token in secure storage, one per gym), refresh shared by concurrent requests, safe retries, the server's clock |
| `src/lib/useAction.ts` | Every button that changes something: one tap is one request (§17.4) |
| `src/lib/live.ts`, `LiveUpdates.tsx` | The WebSocket: sign in by message, renew the token, ping/pong, reconnect with backoff; events re-read the affected screens |
| `src/lib/query.ts` | TanStack Query, its cache kept on the phone: the last data (and the QR) show at once, offline too |
| `src/lib/session.tsx` | The gyms this phone knows, which one is open, signed in or not |
| `src/lib/push.tsx` | Notifications: asked for on tap, registered per gym, off on sign-out, taps open the right screen |
| `src/app/` | The screens; `index.tsx` sends people to choose a gym, sign in, or Home |
