# Notifications on real phones

What to try on an Android phone and an iPhone before a gym relies on
notifications. Tests and emulators cover the code; only real phones show what
a lock screen, an iPhone's Home Screen app and a phone's battery saver do to
them.

| | Who gets them | How |
|---|---|---|
| The member web app | Members, in the browser or added to the Home Screen | Web Push (PLAN.md §16.3, 8.3) |
| The staff dashboard | The owner and the desk | Web Push (§18.6) |
| The phone app | Members, on the Android `.apk` | Expo's push service and Firebase (§17.6, `docs/MOBILE.md` §6) |

## 1. Reach your Mac over HTTPS

Browsers show web notifications only on an `https://` page. A phone on the
Wi-Fi opens the Mac at `http://192.168.x.x:3000`, which isn't. A tunnel gives
the Mac an `https://` address for as long as it runs:

```sh
cd ~/gymbahi
make up
make seed-demo                                  # the demo gym, /demo
cloudflared tunnel --url http://localhost:3000  # or: ngrok http 3000
```

It prints an address like `https://quiet-river-1234.trycloudflare.com`: open
that on the phones. **While it runs, your development server is on the
internet, data and all: stop it (Ctrl+C) when you're done.** Or try it all on
the deployed app (`docs/DEPLOY.md`), which is `https://` already.

Your `.env` already sends real notifications (`PUSH_PROVIDER=webpush` and a
`VAPID_PRIVATE_KEY`). With `PUSH_PROVIDER=console` they're only logged.

The demo gym: the owner is `9800000200`, password `demo-password-123`;
`make seed-demo` ends by printing a member's number, who signs in to the
member app with `MASTER_OTP` from `.env`. Its join form is on, and members can
pay by eSewa, Khalti or bank.

## 2. Android phone (Chrome)

**Staff dashboard**

1. On the phone: `https://<tunnel>/staff`, sign in as the owner.
2. **My account → Notifications → Turn on**, and allow. It says *On for this
   phone or computer*.
3. On the Mac, as a member: `https://<tunnel>/demo`, sign in, **Renew**, choose
   a plan and a way to pay, **I've paid**. On the phone, within seconds:
   *Payment to approve*, with the member's name, amount and plan. Tap it:
   Payment requests opens.
4. A second member pays the same way: the notification is replaced by
   *2 payments to approve*, not added to.
5. The member asks to freeze (**Freeze → Ask the gym**): *Freeze request*.
   Tap: Freeze requests.
6. `https://<tunnel>/demo/join`, filled in: *New enquiry*. Tap: Enquiries.
7. Untick *Freeze requests* in My account and ask to freeze again: nothing
   comes.
8. Sign out on the phone, pay again as a member: nothing comes. Sign in again
   as the owner: they are on again without asking.

**Member web app**

1. On the phone: `https://<tunnel>/demo`, sign in as a member.
2. Home → **Get reminders on this phone → Turn on**, and allow.
3. On the Mac, in the dashboard: **Notices**, publish one. It arrives on the
   phone; tap it: the app's Notices.
4. As the member, pay from the app; approve it in the dashboard's Payment
   requests: the phone says so.

Chrome may also offer to install either one (*Add to Home screen*):
notifications work the same way installed or not.

## 3. iPhone (iOS 16.4 or later)

An iPhone gives web notifications only to a web app on the Home Screen, and
that app has its own sign-in, apart from Safari's.

**Staff dashboard**

1. In Safari: `https://<tunnel>/staff` → **Share → Add to Home Screen → Add**.
   It's called *GymBhai*.
2. Open *GymBhai* from the Home Screen (not Safari), sign in as the owner.
3. **My account → Notifications → Turn on → Allow**.
4. Steps 3 to 8 of the Android list.

**Member web app**

1. In Safari: `https://<tunnel>/demo` → **Share → Add to Home Screen**. Open it
   from there and sign in as a member.
2. Home → **Turn on → Allow**, then publish a notice from the dashboard.

A Home Screen app keeps the address it was added from. cloudflared's address
changes every time it starts: remove the app and add it again when it does.
(ngrok gives a free account one fixed address, which avoids that.)

## 4. The phone app (Android `.apk`)

Already working on the Android emulator (PLAN.md M12); a real phone is
`docs/MOBILE.md` §6, from step 5. The app calls the API directly over the
Wi-Fi, so it needs no tunnel: `make mobile-env`, `make apk`, install, Home →
**Turn on**, publish a notice. iPhone push for the phone app waits for the
paid Apple account.

## 5. What to note

For each: did it arrive, how quickly, with the phone locked and unlocked; is
the wording right (switch the account to Nepali in My account and try one);
does the tap open the right page.

| Check | Android | iPhone |
|---|---|---|
| Staff: payment to approve | | |
| Staff: replaced by *2 payments to approve* | | |
| Staff: freeze request | | |
| Staff: new enquiry | | |
| Staff: an unticked kind stays quiet | | |
| Staff: stops when signed out, back when signed in again | | |
| Member: a notice | | |
| Member: payment approved | | |
| Phone app: a notice | | — |

If one doesn't arrive: is the phone's battery saver or a *Focus* holding it
back; does the phone's Settings → Notifications show the browser or the
Home Screen app as allowed; and does `make logs` on the Mac show the worker
failing to send it (`failed, will retry` or `failed for good`, with the
reason). A send that worked logs nothing.
