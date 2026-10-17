# Maestro flows

The member app driven on a simulator, emulator or phone, as a member uses it
(PLAN.md §17.7, 12.9). Setup and every way to run them: `docs/MOBILE.md` §3.

```sh
make e2e-mobile                                  # iPhone simulator, Expo Go
make e2e-mobile app=host.exp.exponent expo_url=exp://10.0.2.2:8081   # Android emulator, Expo Go
make e2e-mobile app=com.gymbhai.member           # the installed .apk
```

Parameters (`-e NAME=value` when running `maestro` directly):

| | |
|---|---|
| `APP_ID` | `host.exp.Exponent` (Expo Go, iOS), `host.exp.exponent` (Expo Go, Android) or `com.gymbhai.member` (installed app) |
| `CODE` | The sign-in code: `MASTER_OTP` from the root `.env` |
| `EXPO_URL` | Expo Go only: the dev server, `exp://127.0.0.1:8081` by default |
| `GYM` | The test gym, `e2e-app` by default (`make seed-app`) |

Each flow signs in as its own test member, so no number reaches the limit of
three codes in 15 minutes. Screens are found by `testID` where text could
change; `subflows/` holds the shared steps.
