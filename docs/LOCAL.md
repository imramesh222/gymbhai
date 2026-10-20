# Running GymBhai on your Mac: start, stop, new Wi-Fi

The everyday commands for the backend, the web dashboard and the phone app
in development. Setting the phone app up the first time, its tests, and
sharing it with testers are in `docs/MOBILE.md`.

## Start

```sh
cd ~/gymbahi
make up            # database, API, worker and web dashboard (Docker)
make mobile-env    # points the phone app at this Mac's Wi-Fi address
cd mobile
npx expo start     # the phone app's dev server
```

Then:

| What | Where |
|---|---|
| Web dashboard (staff) | http://localhost:3000/staff |
| Web member app | http://localhost:3000/&lt;gym address&gt; |
| API | http://localhost:8001 (from phones: http://&lt;Mac's Wi-Fi address&gt;:8001) |
| Phone app | Open **GymBhai** (the development build) on the phone; pick the Mac's server or scan the QR from `npx expo start` |

The phone must be on the **same Wi-Fi** as the Mac.

## Stop

1. In the terminal running `npx expo start`: **Ctrl+C**.
2. ```sh
   cd ~/gymbahi
   make down
   ```
   Stops the containers. The data stays: the database is as you left it next
   time.
3. Close the iPhone simulator and the Android emulator, if they are open.

## On a different Wi-Fi

The Mac gets a new address on each network, and the phone app has to know it.
Only one setting depends on it: `EXPO_PUBLIC_API_URL` in `mobile/.env.local`.

```sh
cd ~/gymbahi
make mobile-env    # writes the new address into mobile/.env.local
```

Then restart `npx expo start` (Ctrl+C, run it again).

| You use | After changing Wi-Fi |
|---|---|
| The development build (from `eas build --profile development` or `make apk-dev`) | `make mobile-env`, restart `npx expo start`. Nothing to reinstall |
| The test `.apk` (`make apk`) | It has the old address built in: `make mobile-env`, then `make apk`, and install the new file |
| The web dashboard | Nothing: `localhost` works on any network |

Check the phone can reach the Mac: open `http://<Mac's address>:8001/health`
in the phone's browser. It should say `{"status":"ok"}`. To see the
address: `ipconfig getifaddr en0`.

## Handy while testing

| | |
|---|---|
| A fresh test gym | `make seed-app` makes `e2e-app` again (this signs phones out of it) |
| Its owner, in the dashboard | `9800000100`, password `app-test-password-123` |
| A member, in the app | `9800000101` (more in `docs/MOBILE.md` §2); the code is `MASTER_OTP` from `.env` |
| A notification to your phone | Dashboard → Notices → publish: members with notifications on always get one (the SMS tick only adds SMS for the rest) |
| An enquiry | `http://localhost:3000/e2e-app/join`, or *Ask to join* in the app; it shows under Enquiries |
| Pushes only logged, not sent | `PUSH_PROVIDER=console` in `.env`, then `make up` (`webpush` sends for real) |
| Web notifications on a real phone | They need `https://`: a tunnel to the Mac, `docs/PUSH.md` |

## When something doesn't start

| Symptom | Fix |
|---|---|
| `make up` says Docker isn't running | Open Docker Desktop and wait for it to say *running*, then `make up` again |
| `npx expo start` asks to use port 8082 | Another Metro is still running: press **n**, find it with `lsof -nP -iTCP:8081 -sTCP:LISTEN`, stop it (`kill <pid>`), start again |
| The app says "Can't reach GymBhai" | Same Wi-Fi? `make mobile-env` run since changing network? `make up` running? Try the `/health` address above |
| The dashboard won't load | `make ps` shows what's running; `make logs` shows why one stopped |
