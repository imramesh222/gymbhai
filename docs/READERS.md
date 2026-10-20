# Fingerprint and face readers

How a gym's door reader talks to GymBhai (PLAN.md §18.2). Two brands, chosen
for each reader in **Settings → Door scanners → Add a fingerprint or face
reader**: *ZKTeco / eSSL* or *Hikvision*.

**Not yet tried on a real reader.** Both are built to the makers' published
protocols and tested against a simulated reader. Before a gym relies on one,
set it up together and go through [What to confirm on a real
reader](#what-to-confirm-on-a-real-reader).

## What happens, whichever brand

- **Members go on the reader by themselves.** GymBhai puts each member with a
  current, upcoming or recent membership on every reader of the gym, under
  their **reader number**: the digits of their member code (HFC-0048 is 48).
  The member's profile shows it. Staff enrol the member's fingerprint or face
  on the reader under that number, once.
- **Fingerprints and faces stay on the reader.** GymBhai keeps only which
  reader number is which member, and drops any fingerprint template a reader
  sends.
- **Each scan is a check-in** through the same rules as a QR scan, dated when
  the member was at the door (method `fingerprint`, `face`, `card` or `pin`).
  A reader that was offline sends its scans later; each is recorded once.
  Scans from before the reader was added, a reader user who isn't a member
  (staff, say), and scans dated in the future by a wrong clock are ignored.
- **Taken off after 90 days.** A member who stopped coming more than 90 days
  ago, is archived or erased is taken off the reader.
- **Nothing to schedule.** The reader (or bridge) asks for changes every few
  seconds, and GymBhai works out what it should hold when it asks. A
  membership that ends at midnight needs no job.

## ZKTeco and eSSL: ADMS

Readers with **ADMS**, the "cloud server" setting, call GymBhai themselves:
nothing else is needed at the gym.

1. In GymBhai: add the reader with its **serial number** (Menu → System Info,
   or the label on the back). That is how the reader says who it is.
2. On the reader: **Menu → Comm. → Cloud Server Setting**: server address the
   app's domain (for example `app.gymbhai.com`), port `443`, **HTTPS** on.
3. Set the reader's clock to Nepal time: it reports scans in its own time.

It calls `/iclock/cdata`, `/iclock/getrequest` and `/iclock/devicecmd`
(backend/app/api/routes/adms.py); `deploy/Caddyfile` sends `/iclock/*` to the
API.

**Older firmware without HTTPS.** Some readers only speak plain HTTP. Only if
a gym's reader is one of them, add this site to `deploy/Caddyfile`; it sends
reader traffic unencrypted, members' names included, so prefer a reader with
HTTPS:

```
http://{$APP_DOMAIN} {
	handle /iclock/* {
		reverse_proxy api:8000
	}
	handle {
		redir https://{host}{uri} permanent
	}
}
```

**For now a ZKTeco reader doesn't refuse an expired member by itself.**
GymBhai records their scan as `denied_expired`, so the desk sees it (Today,
Attendance, the member's visits), but the door still opens. How to make the
reader refuse a member without deleting their fingerprints (an end date on
the user, or an access group with no hours) depends on the model: the first
thing to confirm.

## Hikvision: the bridge

Hikvision readers are managed through **ISAPI** on the gym's own network,
which GymBhai can't reach from the internet. A small program at the gym, the
bridge, does it: [`bridge/hikvision_bridge.py`](../bridge/hikvision_bridge.py).

1. In GymBhai: add the reader. The dialog shows the bridge's settings with
   the reader's **token**, once: copy them.
2. On a PC or Raspberry Pi on the reader's network, with Python 3.10 or later
   (nothing else to install): save the bridge and its settings as
   `bridge.json`, filling in the reader's address, user name and password.
3. Run `python3 hikvision_bridge.py bridge.json`, and set it to start with the
   machine (a systemd service, or Task Scheduler on Windows).

Every few seconds it collects the reader's changes from GymBhai and makes them
over ISAPI (`UserInfo/SetUp` and `UserInfo/Delete`), then reads the reader's
event log (`AcsEvent`) and passes the scans on. Each member on the reader
carries an **end date**, the last day of their membership, so **the reader
refuses an expired or frozen member by itself**, even if the internet or the
bridge is down.

## What to confirm on a real reader

ZKTeco / eSSL:

1. Which models the pilot gyms have, and whether their firmware has ADMS and
   HTTPS.
2. The reader accepts `DATA UPDATE USERINFO` from `/iclock/getrequest` and
   answers on `/iclock/devicecmd`; names show on its screen.
3. Scans arrive on `/iclock/cdata?table=ATTLOG` in Nepal time, with the verify
   modes GymBhai maps (1 fingerprint, 15 face, 2 card, 0 PIN).
4. How to refuse a member without losing their fingerprints, and add it.
5. Whether `DATA DELETE USERINFO` (after 90 days) also deletes the user's
   fingerprints. GymBhai expects it does.

Hikvision:

1. Which models, and whether they take `UserInfo/SetUp` (newer firmware) or
   need `Record` and `Modify` (older).
2. A user with a past `Valid.endTime` is refused at the door, and their face
   kept.
3. The event search (`AcsEvent`, major 5) returns scans with
   `employeeNoString` and `currentVerifyMode`.
4. Whether the reader needs `doorRight` and `RightPlan` as the bridge sends
   them.
