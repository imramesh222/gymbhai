# GymBhai — implementation plan

*Drafted 2026-09-19. Domain: gymbhai.com.*

One product, used by many gyms. Each gym signs up, manages its members, collects fees and tracks visits; its members get a phone app with their membership, payments and a personal QR code for check-in. Gyms pay us monthly.

## Tech stack

| Layer | Technology |
|---|---|
| **Backend** | FastAPI (Python 3.13), SQLAlchemy 2, Alembic migrations, Pydantic 2 |
| **Frontend** | Next.js (App Router) with **TypeScript** and **Tailwind CSS** — one app for the staff dashboard, member app (PWA), kiosk and platform admin |
| **Database** | PostgreSQL 16 |
| **Containers** | Docker — every part runs in its own container (`db`, `api`, `worker`, `web`), started with Docker Compose in development and on the server; Caddy container in front for HTTPS in production |
| **Tests** | pytest (backend), Vitest + Testing Library (frontend), Playwright (end-to-end) |

Details and the reasons for each choice are in §3.

---

## 1. What version 1 must do

The one thing an owner pays for: **no member trains on an expired membership, and nobody's renewal is forgotten.**

**In v1**
- Gym sign-up (including choosing AD or BS calendar), branches, staff accounts with permissions the owner ticks per person
- Plans: 1 month, 3 months, 6 months, 1 year out of the box, plus any the gym adds; admission fee, discounts
- Members: add at the desk (this is what gives them app access), profile with photo, import an existing register from Excel
- Memberships and renewals, with full history; the owner, and staff they allow, can edit everything, every edit logged
- Payments go **straight to the gym** — cash, or the gym's own eSewa / Khalti / Fonepay / bank QR. The app records them, it never handles the money. Receipts and dues
- Members can renew from the app: pick a plan, pay to the gym's QR, submit the transaction ID; staff approve and it activates
- Expiry list: due this week, lapsed, dues outstanding
- SMS: welcome, renewal reminders before and after expiry, notices
- **QR codes:** one per gym (and per branch) to open the member app, and one per member for check-in
- Check-in at the door by scanning the member's QR, with expired members stopped
- Member app (installable web app): sign in by SMS or email code, days left, their QR, renew, payments, visits, notices
- Today dashboard and monthly reports
- Platform admin (us): all gyms, their subscriptions, SMS credits
- Export: a gym can download its members, memberships, payments and check-ins to Excel at any time — it's their data

**Not in v1** — see [§14 After v1](#14-after-v1)
Automatic payment verification, progress tracking, workout and diet plans, class booking, native app store apps, WhatsApp, offline kiosk, fingerprint and face readers, Nepali language.

---

## 2. Who uses it

| Who | Can do |
|---|---|
| **Platform admin** (us) | Every gym: activate subscriptions, add SMS credits, suspend, reset owner passwords |
| **Owner** | Everything in their gym, every branch, always. Creates staff accounts and decides what each one can do |
| **Staff** | Only what the owner has ticked for them, only in the branches the owner has given them (§2.1) |
| **Member** | Their own membership, QR, payments, visits and notices only |

### 2.1 Staff permissions

There are no fixed roles. The owner creates each staff account — name, phone or email, password — then ticks exactly what that person may do and in which branches. To save time the form offers **starting points** the owner can then change: *Manager* (almost everything, but not training members: that makes someone a trainer), *Front desk* (members and their app access, renewals, selling personal training, payments, check-in), *Trainer* (train members, view members, check members in; §18.3), *Blank*.

| Area | Permission |
|---|---|
| Members | View members · Add members · Edit member details · Archive members · Turn app access on/off |
| Enquiries | Enquiries: add, follow up, convert (§16.4, 9.1; in the *Front desk* starting point) |
| Memberships | Sell and renew · Edit dates, price, discount and plan · Extend days · **Extend everyone** · Freeze · Cancel · Delete |
| Personal training | **Train members**: their own clients and sessions, and in the trainer list · **Sell personal training**, change and cancel it, and anyone's sessions (§18.3) |
| Classes | **Teach classes**: their own rosters and who came, and in the instructor list · **Book classes for members** at the desk · **Manage classes**: the timetable, moving and cancelling a class, the booking rules (§19.4) |
| Progress | **See and record progress**: members' weight and measurements, at their branches (§19.5; in the *Trainer* starting point). Photos are never this: only the trainer a member shares one with sees it |
| Money | Collect payments · **Approve app payments** · Edit payments · Void payments · Record refunds · See money totals and reports |
| Expenses | Record expenses · Edit and void expenses (§18.1) |
| Door | Check members in · Let someone in despite an expired membership |
| Messages | Send notices · Send SMS to a member |
| Gym setup | Plans and prices · Payment methods · Reminder rules · Check-in rules · Devices · Gym settings |
| Staff | Manage staff accounts |

Rules the system enforces:
- The owner always has every permission; nobody can remove or edit the owner.
- A staff member with **Manage staff** can only give permissions they have themselves, and cannot give **Manage staff**.
- Removing a permission or disabling an account takes effect immediately, not at next sign-in.
- Every permission change is in the activity log.

Staff sign in with email or phone and a password. Members sign in with a one-time code sent to the phone or email the gym registered for them — see §5.5.

---

## 3. Architecture

```
                  ┌──────────────────────────────────────────┐
 Browser / PWA ──►│ Next.js (frontend)                       │
                  │  /[gym]        member app (PWA)          │
                  │  /staff        owner & staff dashboard   │
                  │  /kiosk        door scanner              │
                  │  /admin        platform admin            │
                  └───────────────┬──────────────────────────┘
                                  │ JSON over HTTPS
                  ┌───────────────▼──────────────────────────┐
                  │ FastAPI (api)                            │
                  └───────┬───────────────────────┬──────────┘
                          │                       │
                  ┌───────▼───────┐       ┌───────▼──────────┐
                  │ PostgreSQL 16 │◄──────│ worker           │──► SMS gateway
                  └───────────────┘       │ reminders, SMS   │    (Sparrow / Aakash)
                                          └──────────────────┘
```

| Part | Choice | Why |
|---|---|---|
| Backend | FastAPI, SQLAlchemy 2, Alembic, Pydantic 2 | Same as Namaste Desk |
| Database | PostgreSQL 16 | Same; no extensions needed |
| Frontend | Next.js (App Router), TypeScript, React, Tailwind CSS | Same; one app serves staff, members and kiosk |
| Worker | Same Python image, a separate container running a loop every minute | Reminders and SMS sending without adding Redis or Celery |
| Job queue | A `jobs` table in Postgres, claimed with `FOR UPDATE SKIP LOCKED` | Enough for thousands of SMS a day; one less service |
| Live updates | Server-Sent Events (`GET /live`, `GET /m/live`) fed by Postgres `NOTIFY`; each API process `LISTEN`s once and fans out | Screens change when the door, the app or another desk acts — no Redis, works across API workers and through the Next.js proxy and Caddy; events carry ids only and screens reload through the normal API (`backend/app/services/live.py`) |
| SMS | Provider interface: `sparrow`, `aakash`, `console` (dev, prints to log) | Switch providers without touching the rest |
| Files | Local volume in development; S3-compatible storage (e.g. Cloudflare R2) in production | Member photos and gym logos |
| QR generate | `qrcode` (npm) in the browser, `segno` (Python) for printed cards | |
| QR scan | Browser `BarcodeDetector` where available, `@zxing/browser` fallback; USB scanners work as a keyboard | Any phone, tablet or cheap scanner |
| Containers | Docker Compose: `db`, `api`, `worker`, `web` (+ `caddy` in production) | `docker compose up` and it runs; the same images run on the server |

### Tenancy — keeping each gym separate

- Every gym-owned table has a `gym_id`. The signed-in user's token carries their `gym_id`; one FastAPI dependency resolves it, and every query goes through helpers that filter by it. Nothing takes a `gym_id` from the request body.
- Branch access is a second filter: staff limited to certain branches only see those.
- A regression test signs in as gym A and tries to read, change and check in gym B's members by ID; every attempt must fail with 404.
- Postgres row-level security can be added later as a second layer; not needed for v1.

### URLs

| URL | What |
|---|---|
| `app.gymbhai.com/fitness-zone` | Fitness Zone's member app; the gym QR opens this |
| `app.gymbhai.com/staff` | Staff dashboard (gym comes from the login) |
| `app.gymbhai.com/kiosk` | Door scanner on a registered tablet or phone |
| `app.gymbhai.com/admin` | Platform admin |

Each gym's member app has its own web manifest (`/fitness-zone/manifest.webmanifest`), so "Add to Home Screen" installs an icon with **that gym's** name and logo.

---

## 4. QR codes

Two kinds, as decided.

### 4.1 Gym QR (one per gym, one per branch)

- Opens `app.gymbhai.com/<gym-slug>` (branch QR adds `?b=<branch>` so the app starts on that branch's notices).
- Printed as an A4 poster from **Settings → QR poster**: gym logo, "Scan to see your membership", QR.
- Used for: first sign-in, installing the app, a member who lost the welcome SMS.
- Static. Nothing secret in it.

### 4.2 Member QR (one per member)

Each member has a personal QR that is scanned at the door. Two forms of the same identity:

**In the app — changes every 30 seconds.**
- On sign-in the member's phone receives a per-member secret. The app generates a code from it every 30 seconds (the same idea as an authenticator app): `gb1.<member_id>.<time-window>.<signature>`.
- The server accepts the current window and one either side (clock drift).
- Works **with no mobile data** on the member's phone — only the scanner needs internet. Gyms often have poor signal inside.
- A screenshot sent to a friend stops working within a minute.

**Printed card — for members without a smartphone.**
- Static code `gbc.<card_token>`, printed on a card from the member's profile (**Print card**, credit-card size, with photo and member code).
- If lost: **Reissue card** makes a new token; the old card stops working immediately.
- Because a static code can be shared, the scan result always shows the member's **photo** so the desk can check the face.

**How the app code is made:** at sign-in the phone receives a key derived from the member's secret and `qr_version`; it signs `<member>.<30-second window>` with HMAC-SHA256 in plain JavaScript (not WebCrypto, which only exists on HTTPS pages), so the QR draws offline on any phone. The last membership and key are kept on the phone, and a service worker keeps the app shell, so the app opens and shows the QR with no signal. `backend/app/core/qr.py` and `frontend/src/lib/memberQr.ts` share a test vector.

**gb2, since §19.2:** the same changing code signed with Ed25519, `gb2.<member>.<window>.<signature>`. The phone gets a second key at sign-in (`signing_key`) and signs with `@noble/ed25519`; a kiosk holding only the public key can check the code offline but never make one, which an HMAC can't offer. The server accepts both; an app signs gb2 once it has the key.

**Revoking:** each member has a `qr_version`. Bumping it (lost phone, suspected sharing) invalidates the app secret and the card at once; the member signs in again to get a new one.

### 4.3 Scanning at the door

Four ways in v1, all going through one check-in service so more can be added later:

1. **Kiosk** — a tablet or old phone at the entrance, `/kiosk` open, camera always scanning. Members hold up their QR. The screen shows:
   - 🟢 **"Welcome, Sita — 23 days left"** with her photo, or
   - 🟠 **"Welcome, Sita — 3 days left, please renew"**, or
   - 🔴 **"Membership expired on 3 Kartik — please see the desk"**, and the desk's dashboard shows the same alert.
2. **Staff phone** — scanner button in the staff dashboard, same result.
3. **USB/Bluetooth scanner** — these type the code like a keyboard; `/kiosk` has a hidden focused input that accepts it. No camera needed.
4. **Manual** — staff search a name and press Check in, for a dead phone or forgotten card.

**Rules on each scan**
- Membership active → allowed. Expired or frozen → denied (owner can set a grace period of N days, allowed with a warning).
- Plan limited to one branch and scanned at another → denied.
- A visit pack with every visit used → denied (`denied_visits_used`); an off-peak plan outside its hours → denied (`denied_hours`, staff can override). The door shows visits left on a pack (§16.4, 9.3, 9.4).
- Same member scanned again within 3 hours (configurable) → "Already checked in", no duplicate visit.
- Dues outstanding → follows the gym's **dues rule** (§5.3): allow, allow with a warning, or refuse.
- Every scan, allowed or denied, is recorded — denied scans are how owners see who is trying to train unpaid.

**Kiosk registration:** the owner, or staff with the **Devices** permission, opens `/kiosk` on the device while signed in and chooses **"Use this device as the door scanner for <branch>"**. The device receives a long-lived device token (stored on it, revocable from Settings → Devices). The kiosk can only check people in — it cannot open the dashboard.

**Fingerprint and face devices (later).** Many gyms will want a fingerprint or face reader at the door, often wired to a turnstile or door lock. The check-in service is built so a device is just another source of check-ins:
- Readers from common brands (such as ZKTeco) keep the fingerprints and faces **on the device itself**; we store only which device user is which member. No biometric data reaches our server — simpler, and far safer for members' privacy.
- The device reports each scan to us, and we record it with the same rules as a QR scan.
- For a door that locks, we push the list of members allowed in to the device, so an expired membership is refused at the door even if the internet is down.
- Which devices to support is decided later (§15); nothing in v1 needs to change for it.

**Offline (M17, §19.2):** the kiosk keeps a roster and decides by itself for up to the gym's *kiosk offline days* (3 unless changed), then sends the scans when the internet is back. Without a roster (a new kiosk with no internet yet) the desk checks people in by hand, as before.

---

## 5. Plans, payments and activation

### 5.1 Plans

Every new gym starts with four plans, prices left blank for the owner to fill in:

| Plan | Duration |
|---|---|
| 1 month | 1 month |
| 3 months | 3 months |
| 6 months | 6 months |
| 1 year | 12 months |

The owner can rename them, set prices, hide any, and add their own ("Morning only — 3 months", "Couple — 1 year", "Student — 1 month"). Each plan has a duration, price, one-time admission fee, and which branches it covers.

- **Calendar — each gym chooses, there is no default.** On sign-up the owner picks:
  - **Count plans in:** AD months (a 3-month plan from 15 January ends 14 April) or BS months (from 5 Baisakh ends 4 Shrawan). BS months are 29–32 days long, so BS counting uses the BS calendar, not 30 days × N.
  - **Show dates in:** AD, BS, or both — on every screen, receipt, SMS and the member app.
  - Both can be changed later in Settings. Changing how plans are counted only affects memberships sold after the change; existing end dates never move.
- **Price is copied onto each membership when it's sold.** Raising a plan's price later never changes what existing members paid or owe.

### 5.2 How members pay

**The app never touches the money.** Members pay the gym directly, the way they already do; the app records it.

| Way | What happens |
|---|---|
| **Cash at the desk** | Staff take the cash and record it → membership activates |
| **Gym's QR at the desk** | Member scans the gym's own eSewa / Khalti / Fonepay / bank QR standee with their wallet app. Staff see the money arrive on their phone and record it with the transaction ID → membership activates |
| **From the member app** | Member picks a plan → app shows the gym's payment QR and account details → member pays in their wallet app → enters the transaction ID and/or uploads the screenshot → "Sent — waiting for the gym to confirm" → staff approve (§5.4) → membership activates |

Why not a payment gateway in v1: no merchant integration, no licence, no fees, and money never passes through us — gyms trust it because it's exactly what they do today. Automatic verification through Fonepay or eSewa merchant APIs is a later add-on (§14).

**Settings → Payment methods:** the owner uploads each QR image (eSewa, Khalti, Fonepay, bank) with the account name and number. These show in the member app's Renew screen and can be printed as a desk standee.

### 5.3 Activating a membership at the desk

One screen, about 30 seconds:

1. **Find the member**, or add a new one: name and phone required; email and photo optional.
2. **Choose a plan.** Start date defaults to today — or, if they still have time left, the day after their current membership ends, so early renewers lose nothing. End date fills in automatically; staff can change either.
3. **Price** fills in from the plan. Add a discount; the admission fee is added on a first membership and can be waived.
4. **Payment received now:** full, part, or nothing yet — method and transaction ID.
5. **Save.** The membership is active from the start date, a receipt is produced, and the member gets an SMS: *"Your 3-month membership at Fitness Zone is active until 4 Shrawan. Open your app: …"*

Part payment leaves **dues**, shown on the member's profile, the Today screen and the member app.

Gym setting **dues rule** — what happens at the door while a member owes money: *allow*, *allow with a warning* (default), or *refuse until paid*. One setting, used by both the desk and the door.

### 5.4 Activating from an app payment

A red count on **Payment requests** in the staff dashboard shows how many are waiting. Each shows the member, plan, amount, method, transaction ID, screenshot and time sent. Staff with the **Approve app payments** permission (§2.1) check the gym's eSewa / bank app for the money, then:

- **Approve** → the membership is created exactly as at the desk (start = day after the current one ends, or today), the payment is recorded with the transaction ID, and the member gets an SMS and sees it active in the app.
- **Reject** with a reason ("amount not received", "wrong amount") → the member sees the reason in the app and by SMS.

Safeguards: a transaction ID can only be used once per gym; if the amount doesn't match the plan price, staff must adjust the price or record a part payment before approving; every approval records who approved it.

### 5.5 Who can sign in to the member app

**Only people the gym has added. There is no self sign-up.**

- **Adding a member with a phone number is what gives them access.** Email is optional; if given, the member can also sign in with a code sent by email (email codes cost nothing, SMS codes use credit).
- The welcome SMS carries the gym's link.
- A number the gym hasn't added gets: *"This number isn't registered with Fitness Zone. Please ask at the desk."* It never reveals whether the number belongs to another gym.
- **One phone, several members:** a parent and children often share a number. Staff are warned when adding a phone that's already on file, but can go ahead. Signing in with that number asks *"Who are you?"* and lists the names; each keeps their own membership and QR.
- The same person at two gyms is two separate members with two separate logins; each gym's link only knows its own members.
- **Expired members can still sign in** — to see that they've expired and renew from the app — but their QR is refused at the door.
- **Or at the desk, with no code** (§18.4): staff open the member's profile → *Sign in on their phone* and show a QR; the member scans it with the phone's camera, or with *Scan the QR at the desk* on the sign-in screen. No SMS, so it costs nothing and works before a gateway is set up.

Controls on the member's profile:

| Control | Effect |
|---|---|
| **App access** on / off | Off blocks sign-in and signs out their devices (e.g. a banned member) |
| **Sign in on their phone** | A one-time QR at the desk, no SMS code (§18.4) |
| **Change phone or email** | Old one stops working immediately; devices signed out |
| **Resend welcome** | Sends the link again |
| **Sign out all devices** | Lost phone |
| **Reissue QR / card** | See §4.2 |

*Later, optional:* a **Join request** form behind the gym QR that staff approve — off by default, for gyms that want online enquiries.

### 5.6 What gym admins can edit

The owner can change **everything** about a membership. Staff can do each action below only if the owner has ticked that permission for them (§2.1).

| Action | Notes |
|---|---|
| Change start or end date | Correct a mistake, give extra days |
| Extend by N days | Reason required, e.g. "injury — 10 days" |
| **Extend everyone** | Gym closed 7 days for Dashain → every active membership (or one branch's) extended by 7 days in one action |
| Change plan | Upgrade 1 month → 3 months mid-way: new end date and price recalculated, the difference shows as dues to collect |
| Change price, discount, admission fee | Dues recalculate |
| Freeze / unfreeze | End date moves by the frozen days automatically |
| Move to another branch | |
| Cancel | Reason required; a refund, if any, is recorded as a refund payment |
| Edit a payment | Amount, method, date, transaction ID |
| Void a payment | Reason required; owner only by default |
| Delete a membership made by mistake | Only while it has no check-ins; otherwise cancel it |
| Edit member details, photo, phone, email | |
| Archive a member | Hidden from lists, history kept |
| Erase a member | Owner only, at the member's request, can't be undone: personal details gone for good, the gym's accounts kept (§11) |

**Every edit is recorded — who, when, what it was before and after** — and shown in a **History** tab on the membership. Nothing is silently overwritten, which is what makes it safe to let admins edit anything.

### 5.7 How gyms pay us

Same approach as members paying gyms: no gateway in v1.

- **Free trial:** 14 days from sign-up (the day of sign-up and 13 more, in Nepal time), full features, no payment details asked. A trial is a `gym_subscriptions` row with no platform plan, so it works before any price is set.
- **Paying:** the owner pays our eSewa / bank QR and sends the transaction ID from **Settings → Subscription** (or tells us). We check and activate from `/admin`; they get an SMS and email.
- **Before it ends:** the owner sees a banner and gets an SMS 7 and 2 days before.
- **If it lapses:** 7 days' grace with a red banner, then the staff dashboard becomes **read-only** (enforced in `require()` for every change; the API answers 402 `subscription_lapsed`) — they can see and export everything but can't add members, renew or take payments until they pay.
- **Members are never punished for the owner's unpaid bill:** the member app and door check-in keep working, so the gym never has an angry queue at the entrance. That protects our reputation with the gym's members too.
- **Too many members for their tier:** a warning, never a lock-out; we talk to them about upgrading.
- **Suspending** a gym (from `/admin`, for abuse) is different from an unpaid bill: staff can't sign in, and the member app and door stop too.
- Reminders to the owner (7 and 2 days before, and when grace starts) and admin notices are SMS from us: they never use the gym's credits. The optional 8 pm daily summary is the gym's own SMS and does.
- Where gyms pay us is configured with `PLATFORM_PAY_TO_NAME`, `PLATFORM_PAY_TO_ESEWA` and `PLATFORM_PAY_TO_BANK`.
- **SMS credits** are topped up the same way and run separately; when they run out, reminders and notices stop and the owner is told — nothing else is affected.
- **Sign-in codes are never blocked** by a gym's SMS credit or subscription — they're on us (and rate-limited, §11), because a member who can't sign in can't see their QR at the door.

---

## 6. Data model

All tables have `id` (UUID), `created_at`, `updated_at`. Gym-owned tables have `gym_id`, indexed.

**Gyms and people**

| Table | Key columns |
|---|---|
| `gyms` | `slug` (unique), `name`, `logo_key`, `brand_color`, `phone`, `address`, `sms_sender_name`, `terms_accepted_at`, `terms_version` (the terms and privacy policy accepted at sign-up), `settings` (JSON: plan month counting AD/BS, date display AD/BS/both, dues rule (allow / warn / refuse), grace days, re-scan window, reminder language, `require_two_step` — owner only, §11), `status` |
| `branches` | `gym_id`, `name`, `address`, `phone`, `is_active` |
| `staff_users` | `gym_id` (null for platform admin), `name`, `email`, `phone`, `password_hash` — `email` and `phone` unique across all staff, so signing in never needs a gym name — `is_owner` (at most one per gym), `is_platform_admin`, `permissions` (list of permission keys, §2.1), `is_active`, `last_login_at`, `totp_nonce`, `totp_enabled_at`, `totp_last_step` (two-step sign-in, §11); `changelog_seen_at` (What's new, §16.5 10.4); `language` (null = the gym's, §16.6); `muted_notifications` (the kinds of notification turned off, §18.6) |
| `staff_branch_access` | `staff_user_id`, `branch_id` — empty means all branches |
| `members` | `gym_id`, `home_branch_id`, `member_code` (e.g. `FZ-0042`, unique per gym; the prefix is a gym setting, derived from the gym's initials at sign-up), `name`, `phone` (**not** unique — family members often share one number), `email`, `gender`, `date_of_birth`, `address`, `emergency_contact`, `photo_key` (a storage key, served by signed link), `joined_on`, `notes`, `app_access` (bool), `qr_secret`, `qr_version`, `card_token`, `is_archived`, `erased_at` (§11); `referred_by_id` (a member who sent them, §16.4 9.6); `language` (null = the gym's); `height_mm` (for BMI on their progress, §19.5) |
| `leads` | `gym_id`, `branch_id`, `name`, `phone`, `email`, `source` (walk_in, phone, facebook, instagram, tiktok, referral, other), `plan_id`, `status` (new → contacted → trial → joined, or lost), `follow_up_on`, `lost_reason`, `assigned_to`, `trial_on`, `referred_by_id`, `member_id` (once joined), `notes`, `created_by`, `from_ip` (join form only, cleared after a day) — §16.4, 9.1 |

**Money and memberships**

| Table | Key columns |
|---|---|
| `plans` | `gym_id`, `name`, `duration_months` *or* `duration_days`, `price` (null until the owner sets it; such a plan can't be sold without a price entered at the desk), `admission_fee`, `all_branches`, `is_active`, `sort_order` — four seeded on sign-up (§5.1); `visit_limit` (a visit pack, null = unlimited) and `access_hours` (`[{days, from, to}]` in Nepal time, 0 = Monday; null = any time) — §16.4, 9.3, 9.4; `seats` (people one sale covers, 1–6; never with `visit_limit`) — §19.1; `classes` (none, all, chosen) and `class_type_ids` — the classes it lets one book, §19.4 |
| `plan_branches` | `plan_id`, `branch_id` — the branches a plan covers when `all_branches` is false |
| `memberships` | `gym_id`, `member_id`, `plan_id`, `plan_name` (copied at sale, like the price), `branch_id`, `start_date`, `end_date`, `price`, `discount`, `admission_fee`, `cancelled_at`, `cancel_reason`, `created_by`, `source` (desk, app_request, import); `visit_limit` and `access_hours` copied from the plan at sale. A visit pack with every visit used counts as ended, from the let-in check-ins on it; `group_id` (a family or couple plan, §19.1: the payer's membership carries the price and payments, the others 0); `classes` and `class_type_ids` copied from the plan (§19.4) |
| `membership_groups` | `gym_id`, `plan_id`, `payer_member_id`, `seats` (copied from the plan), `created_by` — one sale for several people; each has their own membership (§19.1) |
| `membership_freezes` | `gym_id`, `membership_id`, `from_date`, `to_date` (inclusive), `reason` — extends `end_date` by the frozen days; ending a freeze early gives the unused days back |
| `payments` | `gym_id`, `member_id`, `membership_id` *or* `pt_package_id` (personal training, §18.3; never both), `kind` (payment, refund), `amount`, `method` (cash, esewa, khalti, fonepay, bank), `transaction_ref` (unique per gym when set), `paid_at`, `receipt_no` (sequential per gym), `received_by`, `note`, `voided_at`, `voided_by`, `void_reason` — a payment can't exceed what is owed on its membership or package, nor a refund what was paid |
| `pt_plans` | `gym_id`, `name`, `kind` (monthly, sessions), `sessions` (a pack's size; null for monthly), `duration_months` *or* `duration_days`, `price`, `is_active`, `sort_order` — the gym's personal training plans (§18.3) |
| `pt_packages` | `gym_id`, `member_id`, `plan_id`, `plan_name`, `kind`, `sessions` and `price` copied at sale, `discount`, `trainer_id` (a staff account), `branch_id` (the member's home branch unless chosen), `start_date`, `end_date`, `cancelled_at`, `cancel_reason`, `created_by` — personal training sold; status computed, never stored (§18.3) |
| `class_types` | `gym_id`, `name`, `minutes`, `places`, `color`, `is_active`, `sort_order` — Zumba, yoga (§19.4) |
| `class_slots` | `gym_id`, `branch_id`, `type_id`, `weekday` (0 is Monday), `starts` ("HH:MM", Nepal), `minutes`, `places`, `instructor_id`, `is_active` — the weekly timetable |
| `classes` | `gym_id`, `branch_id`, `type_id`, `slot_id` (unique with `starts_at`: made once), `starts_at`, `ends_at`, `instructor_id`, `places`, `cancelled_at`, `cancel_reason` — each class, made 4 weeks ahead |
| `class_bookings` | `gym_id`, `class_id`, `member_id` (one live booking per class), `status` (booked, waitlist, cancelled), `booked_at` (the queue's order), `cancelled_at`, `late`, `attended` (the instructor's tick; null until then), `source` (app, desk), `booked_by` |
| `progress_entries` | `gym_id`, `member_id`, `measured_on`, `weight_g`, `body_fat` (tenths of a percent), `chest_mm`, `waist_mm`, `hips_mm`, `arm_mm`, `thigh_mm`, `note`, `recorded_by` (staff; null when the member recorded it) — §19.5 |
| `progress_photos` | `gym_id`, `member_id`, `taken_on`, `pose` (front, side, back), `photo_key`, `shared` (with the trainers of their personal training) — private to the member; deleted with them when erased |
| `pt_sessions` | `gym_id`, `package_id`, `trained_on` (a Nepal day within the package's dates), `trainer_id` (the package's trainer that day), `recorded_by`, `note` (cleared when the member is erased), `voided_at`, `voided_by`, `void_reason` — never more than a pack holds; never deleted, only voided (§18.3) |
| `expenses` | `gym_id`, `branch_id` (null = the whole gym), `category` (rent, salaries, electricity, water, internet, equipment, repairs, cleaning, marketing, fees, other), `amount`, `spent_on` (a Nepal day, not after today), `method` (as payments), `paid_to`, `note`, `created_by`, `voided_at`, `voided_by`, `void_reason` — money the gym spent; never deleted, only voided (§18.1) |
| `gym_payment_methods` | `gym_id`, `kind` (esewa, khalti, fonepay, bank, other), `label`, `account_name`, `account_number`, `qr_image_key`, `is_active`, `sort_order` — the gym's own accounts, shown to members |
| `payment_requests` | `gym_id`, `member_id`, `plan_id`, `payment_method_id`, `amount`, `transaction_ref`, `screenshot_key`, `status` (pending, approved, rejected, withdrawn), `reviewed_by`, `reviewed_at`, `reject_reason`, `membership_id`, `payment_id`, `with_member_ids` (a family plan's others, worked out by the server, §19.1) — a member's "I've paid" from the app (§5.4) |
| `freeze_requests` | `gym_id`, `member_id`, `membership_id` (the one covering the first day), `from_date`, `to_date`, `reason`, `status` (pending, approved, rejected, withdrawn), `reviewed_by`, `reviewed_at`, `reject_reason`, `freeze_id` (the freeze approving it made) — one pending per member; the app allows up to 90 days, longer at the desk |
| `idempotency_keys` | `gym_id`, `key` (unique per gym), `route`, `request_hash`, `status_code`, `response` — the answer to each money request, saved in the same transaction as the payment so a repeat replays it (§11); kept a day |
| `gym_counters` | `gym_id`, `name` (`member_code`, `receipt_no`), `value` — row-locked increment so two desks never issue the same number |

**Decisions baked in**
- **Membership status is computed from dates, never stored** (active / upcoming / expired / frozen / cancelled). Nothing can drift out of date, and no nightly job is needed to "expire" anyone.
- **Renewal = a new `memberships` row.** Renewing early starts the day after the current one ends; renewing after a lapse starts today (staff can backdate). History is never overwritten.
- **Dues** = `price − discount + admission_fee − sum(non-voided payments) + sum(refunds)`. Part payments are normal in Nepali gyms.
- **Payments are never deleted**, only voided with a reason — by the owner, or staff given **Void payments** — and logged.
- Money stored as integer paisa to avoid rounding errors.
- **A member's status follows back-to-back renewals.** Days left run to the end of the chain of memberships that start the day after the previous one ends, so an early renewer shows "40 days left", not "10".
- **Check-in rules** (dues rule, grace days, re-scan window) have their own endpoint, `PATCH /gym/check-in-rules`, so they sit behind the *Check-in rules* permission rather than *Gym settings*.

**Visits, messages, devices**

| Table | Key columns |
|---|---|
| `check_ins` | `gym_id`, `branch_id`, `member_id`, `membership_id`, `at`, `method` (app_qr, card_qr, manual; later fingerprint, face), `result` (allowed, warned, override, duplicate, denied_expired, denied_frozen, denied_branch, denied_dues, denied_visits_used, denied_hours), `device_id`, `staff_user_id`, `note` (the reason for an override); `offline` and `client_id` (unique per device): decided by a kiosk with no internet and sent later (§19.2) |
| `devices` | `gym_id`, `branch_id`, `name`, `kind` (kiosk, zkteco, hikvision; §18.2), `serial` (a reader's, unique), `token_hash`, `last_seen_at`, `revoked_at`; for a reader `synced_at` and `command_seq` |
| `reader_users` | `gym_id`, `device_id`, `member_id`, `pin` (their reader number: the digits of their member code), `name`, `on_reader`, `until` (the last day the reader should let them in), `command_id`, `sent_at`, `done_at`, `error` — what GymBhai last told a reader about a member (§18.2); fingerprints and faces stay on the reader |
| `notices` | `gym_id`, `branch_id` (null = all), `title`, `body`, `published_at`, `send_sms` (also SMS the members push can't reach; push to the rest goes with every notice, free), `sms_count`, `push_count` |
| `push_subscriptions` | `gym_id`, `member_id`, `endpoint`, `p256dh`, `auth`, `user_agent`, `last_ok_at`, `revoked_at` — one per browser per member (a shared phone has one each); revoked on turning off, signing out, or when the push service answers 404/410; deleted when the member is erased |
| `reminder_rules` | `gym_id`, `trigger` (expiry · lapsed · dues · not_visiting · birthday; pt_ending · pt_dues, §18.3; progress, §19.5), `days` (for expiry: from the chain's end, −7, −3, 0, +3…; lapsed: days since it ended; dues: days since the sale; not visiting: days without a visit; birthday: 0), `template`, `enabled`. Unique per gym, trigger and days |
| `reminder_log` | `gym_id`, `rule_id`, `dedupe_key`, `member_id`, `membership_id` (null for not visiting and birthday), `sms_message_id` — unique per rule and `dedupe_key` (`membership:<id>`; `visit:<member>:<last visit date>`, once per spell away; `birthday:<member>:<year>`), so nothing is sent twice |
| `scheduled_runs` | `name`, `run_on` — unique pair; how several workers agree a daily task runs once a day |
| `sms_messages` | `gym_id`, `member_id`, `to`, `body`, `kind` (otp, welcome, reminder, notice, receipt), `status`, `provider_ref`, `segments`, `error`, `sent_at` |
| `jobs` | `kind`, `payload`, `run_at`, `attempts`, `locked_at`, `done_at`, `error` |

**Sign-in and audit**

| Table | Key columns |
|---|---|
| `otp_codes` | `gym_id`, `channel` (sms, email), `destination`, `code_hash`, `expires_at`, `attempts`, `consumed_at`, `ip` — a row is written even for an unknown number, so the rate limits also count guessing |
| `login_attempts` | `identifier` (email or phone as stored), `ip`, `succeeded`, `at` — every staff sign-in try, for the limits in §11; kept a day |
| `staff_password_resets` | `staff_user_id` (null when nobody has that email or phone), `identifier`, `code_hash`, `expires_at`, `attempts`, `consumed_at`, `ip` — "forgot password" codes (§11); only the latest for an email or phone can be used |
| `staff_recovery_codes` | `staff_user_id`, `code_hash`, `used_at` — ten single-use codes for a lost phone; only hashes kept |
| `staff_sessions` | `staff_user_id`, `refresh_token_hash`, `previous_token_hash`, `rotated_at`, `user_agent`, `ip`, `expires_at`, `last_used_at`, `revoked_at` — one row per signed-in staff device; the refresh token rotates on every use (§11) |
| `staff_push_subscriptions` | `staff_user_id`, `session_id` (the sign-in that turned it on; null once that session is deleted), `endpoint`, `p256dh`, `auth`, `user_agent`, `last_ok_at`, `revoked_at` — a browser that takes a staff member's notifications (§18.6), sent to only while its session is live |
| `member_sessions` | `member_id`, `refresh_token_hash`, `previous_token_hash`, `rotated_at`, `device_label`, `expires_at`, `last_used_at`, `revoked_at` |
| `member_sign_in_links` | `gym_id`, `member_id`, `token_hash` (unique), `created_by`, `expires_at`, `used_at` — the desk's sign-in QR (§18.4): once, for 5 minutes, only the newest per member; kept a day past expiry, deleted when the member is erased |
| `activity_log` | `gym_id`, `actor_type`, `actor_id`, `action`, `entity`, `entity_id`, `changes` (JSON, before → after), `reason`, `ip`, `at` — powers the History tab (§5.6) |

**Our billing (gyms paying us)**

| Table | Key columns |
|---|---|
| `platform_plans` | `name`, `max_active_members`, `max_branches`, `monthly_price`, `included_sms`, `is_active` — **all prices live here and are edited from `/admin`; none are written into the code**, so pricing can be set and changed any time |
| `gym_subscriptions` | `gym_id`, `platform_plan_id`, `starts_on`, `ends_on`, `status` |
| `subscription_payments` | `gym_id`, `kind` (subscription, sms), `platform_plan_id`, `months`, `sms_credits`, `amount`, `transaction_ref`, `screenshot_key`, `status` (pending, approved, rejected), `submitted_by`, `reviewed_by`, `reviewed_at`, `reject_reason` — an owner's "we've paid you", for a plan or for SMS credits (§5.7) |
| `changelog_entries` | `title`, `body`, `published_at` (null = draft), `created_by` — ours, not a gym's (§16.5, 10.4) |
| `gym_referrals` | `gym_id` (the gym that sent), `referred_gym_id` (unique: once each), `status` (pending → ready once the referred gym's first payment is approved → rewarded or rejected), `ready_at`, `reviewed_at`, `reviewed_by`, `note` (§16.5, 10.5) |
| `member_imports` | `gym_id`, `filename`, `status` (preview, committed), `headers`, `rows`, `mapping`, `result`, `created_by`, `committed_at` — an uploaded register, checked before anything is saved |
| `sms_credit_ledger` | `gym_id`, `change`, `reason`, `balance_after`, `sms_message_id` — top-ups and each SMS sent. The balance is the sum of `change` (rows written in one transaction share a timestamp, so "the latest row" is not reliable); changes lock the gym row so two sends can't spend one credit |

---

## 7. Screens

### How they look

One design system, defined as tokens in `frontend/src/app/globals.css` — brand ramp, canvas and surface colours, the `hairline` border, the card shadows — and built into the shared components (`Button`, `Card`/`ListCard`/`Stat`/`EmptyState`, `Field`, `Choice`, `StatusBadge`, `Dialog`, the inputs). Screens compose those; they don't invent their own colours or borders, so the whole product restyles from one file. Type is Inter, self-hosted by `next/font`.

Staff screens are light and dense — read all day in a bright room, with white cards on a cool canvas. On a laptop the menu is a left sidebar in four groups (Desk; Money and numbers; Messages; Gym) that folds to icons; on a phone, a bottom bar with the four screens the person uses most and **More** for the rest. **Search** (Ctrl/⌘+K or /, or the box in the sidebar) finds a member by name, phone or code from any screen, with Renew and Check in on each result. Shared pieces (`src/components/ui`): toasts after every save, one confirmation dialog (typed confirmation for what can't be undone), a More menu, tabs kept in the address, a table that becomes cards on a phone, skeletons while loading, and a sticky save bar. Charts (`src/components/charts`) are hand-built SVG — columns, lines, a heatmap, sparklines — with colours validated for colour-blind readers, a hover and keyboard readout, and a table view of every chart. The member app is deliberately bolder: a full-bleed header in the gym's own brand colour, the QR as the largest thing on the screen, big touch targets, an icon tab bar. The kiosk is dark and legible across a room. `/admin` keeps the dark bar so our console is never mistaken for a gym's dashboard.

### Staff dashboard (`/staff`)

| Screen | What's on it |
|---|---|
| **Today** | Quick actions (Add member, Scan, Collect payment). A **setup checklist** for new gyms until done or hidden (plans priced, payment account, first member, QR poster, logo, a staff account). **To do**, each with its button: app payments to approve, who ends today (Call, Remind by SMS), who owes most (Collect), who was turned away. Check-ins and money collected compared with the same time yesterday, active members, dues owed; check-ins by hour today; who's probably inside (checked in within 2 hours — there's no check-out); money collected by method. **Enquiries to call back** today or overdue (with Enquiries permission). **Get notified on this device**, once, for staff who'd get notifications (§18.6), until on or put away with *Not now* |
| **Members** | Search by name, phone or code; filters with their counts (all, active, ending this week, expired, owe money, frozen, archived — `?filter=` in the address); a table on a laptop (member, plan, status, owes, last visit; sorted on the server by name, dues or last visit) and cards on a phone; pick members to send one SMS. **Add member**; More: **Extend everyone** (empty to start, says how many memberships first and that number is typed to confirm), Import / export |
| **Member profile** | Header: photo, name, code, status, days left, dues; **Renew**, **Collect payment** (when owing), **Check in**, and **More** (edit, freeze, send SMS, print card, app access, sign in on their phone with a QR (§18.4), resend welcome, sign out all devices, reissue QR and card, archive, erase). Overview shows when they last signed in to the app. Tabs kept in the address: Overview, Memberships, **Personal training** (§18.3; for staff who sell it, or when they have some), Payments (personal training's marked), **Visits** (a month calendar in the gym's calendar, turned-away days marked), Messages (SMS sent), History (personal training's too) |
| **Add member / Renew** | One screen: member details → plan → discount → payment taken now (full or part) → save. Sends the welcome or renewal SMS and prints or shares the receipt |
| **Personal training** | §18.3: **My clients** for a trainer — upcoming and active packages, sessions left or so far, ends on, last session, **Record session** — and **All**, by trainer, for staff who sell it. Search (Ctrl K) has *Record a training session* for trainers |
| **Follow up** | Tabs: **ending soon** (today, this week) · **lapsed** in the last 30 days · **owe money** (memberships, and personal training in a list of its own, §18.3) · **not visiting** (active, no visit for the gym's N days, default 14; joined less than N days ago doesn't count). Each row shows the last visit, **Call**, **WhatsApp** (§18.5) and **Send message**. Was *Expiring*; `/staff/expiring` redirects |
| **Enquiries** | A board by status (New · Contacted · Trial · Joined · Didn't join), a list, and a report by source (enquiries, trials, joined, joined %) with the members who sent the most people. **Add enquiry** warns when the number is already a member or asked before. Each enquiry: call, *Called them*, *Trial visit today*, call-back date and notes, *I'll follow up*, *Didn't join* with a reason, and **Convert to member**, which opens Add member filled in and links the two. Joined and lost ones leave the board after 90 days |
| **Payment requests** | Members' app payments waiting for approval: amount, transaction ID, screenshot. **Approve** / **Reject** (§5.4). Red count in the menu |
| **Freeze requests** | Members asking from the app to pause their membership (dates, reason), for staff with **Freeze**, with a count in the menu. **Approve** makes an ordinary freeze (the end date moves by those days); **Reject** with a reason the member sees. Pending / approved / rejected |
| **Payments** | All payments, filter by date, method, staff; daily cash total for closing the till; edit or void (§5.6) |
| **Expenses** | A month of the gym's own calendar: spent, and spent by category; every expense (date, category, paid to, method, branch, who recorded it); **Add expense**, and on each one Edit, *Same again* (the form filled in, dated today) and Void (§18.1) |
| **Membership edit** | Every field in §5.6, plus **Extend everyone**, and a **History** tab showing each change, who made it, before and after |
| **Attendance** | Last 7, 30 or 90 days; check-ins by day as bars; a weekday × hour heatmap of the busiest hours; denied scans |
| **Reports** | Monthly: income, **spent** and **profit** (income − spent), income by method, spent by category, new members, renewals, lapsed, active count, renewal rate — each against the month before; for a gym with personal training, its own figures (§18.3). Charts of the last 12 months: money in and out, active members, new vs lapsed, renewal rate. Prints |
| **Notices** | Write a notice, choose branches. Every notice goes as a free notification to members who turned notifications on; optionally also by SMS to the rest (shows SMS cost first). Decided 2026-10-18: push used to wait for the SMS tick |
| **Automations** | Messages → Automations: one card per trigger (before/on the day it ends · win back · money still owed · not visiting · birthday; and for personal training, before/on the day it ends · money still owed, §18.3), each rule with an on/off tick, its days, its wording and SMS count; added ones start off. Also the desk SMS wording (welcome, membership sold). Was *Settings → Reminders*, which redirects |
| **Staff** | Staff accounts: add, disable, reset password; permission checklist and branch access per person, with *Manager* / *Front desk* / *Trainer* / *Blank* starting points |
| **Subscription** | Their plan with us, days left, pay and submit transaction ID, SMS credit balance and top-up |
| **Settings** | One page each, with a menu: gym profile and calendar (warns before leaving with unsaved changes), plans and prices, personal training plans (§18.3), payment accounts and QR images, branches, check-in rules (including "not visiting" days), door scanners (kiosks, and fingerprint and face readers, §18.2) and the QR poster, security (owner). Plans can be visit packs (*Visits allowed*) and off-peak (*Only at certain hours*: days and times). Settings → Gym has *Let people ask to join from the gym QR* (off by default) |
| **Import / Export** | Upload an Excel/CSV register, map columns, preview, import members with their current expiry dates. Download members, memberships, payments, expenses and check-ins as Excel. Dates in a register may be AD or BS (a year of 2050 or more is read as BS). Imported memberships carry no price — what members paid before GymBhai isn't income in GymBhai — and no SMS is sent until the gym chooses "Resend welcome" |

### Member app (`/<gym-slug>`)

| Screen | What's on it |
|---|---|
| **Sign in** | Phone number (or email) → 6-digit code. If several members share that phone — a parent and their children — pick who you are. Or **Scan the QR at the desk**, with no code (§18.4); opening the desk's QR link with the phone's camera does the same |
| **Home** | Days left (large ring), expiry date in the gym's calendar setting, **their QR code**, their **personal training** (plan, trainer, sessions or days left, anything owed on it; §18.3), visit streak, latest notice. **Get reminders on this phone** (push), until turned on or put away with *Not now*; on an iPhone not opened from the Home Screen, how to add it first (iOS 16.4+). **Right now: Quiet / Normal / Busy** at their branch — the last two hours' visits against the same two hours on the same weekday over four weeks (hidden until there's enough history, or if the gym turns it off in Settings → Gym). **Add the app to your Home Screen**: Android's own install prompt, or the steps on an iPhone |
| **Renew** | Plans with prices → the gym's payment QR and account details → enter transaction ID or upload screenshot → *waiting for confirmation* → active, or the reason it was rejected. Steps shown at the top: Plan → Pay → Send proof. Plan cards show the price a month and *Save Rs X vs monthly* against the cheapest one-month plan |
| **Payments** | Every payment and receipt (**Download receipt** as PDF), dues if any, pending requests |
| **Visits** | Calendar of visits, count this month |
| **Notices** | From their gym |
| **Profile** | Their details: they change their own **photo**, **emergency contact** and **email** (a code to the new address first, so a borrowed phone can't add someone else's email); name and mobile number at the desk. Each change is logged with the member as the one who made it, **Reminders on this phone** on/off (or why it can't be: unsupported, blocked, not installed on iPhone), sign out (which turns this phone's push off first) |

### Kiosk (`/kiosk`)

Full screen camera, large result card for 3 seconds, then back to scanning. Gym logo and clock when idle.

### Platform admin (`/admin`)

**Home:** monthly recurring revenue, gyms by state (trial, paying, grace, read-only, suspended), trials that start paying, paying gyms lost by month, SMS credits sold by month, and how many gyms are going quiet (§16.5, 10.1).

**Gyms list** with plan, active members, SMS balance, subscription end, and each gym's health: last staff sign-in, visits this week, members added in 30 days, a *going quiet* flag (no sign-in and no visits for a week, past its first week), and its setup checklist (10.2). Activate or extend a subscription after payment, top up SMS credits, suspend, reset an owner's password.

**What's new:** write, publish (or keep as draft) and delete entries (10.4). **Gym referrals:** gyms that sent us gyms; once the new gym has paid, *Give both a free month* (10.5).

Staff side: **Help and guides** (WhatsApp / Viber to `SUPPORT_WHATSAPP`, and short how-tos in `help.en.ts`), **What's new** with a dot until read, and on Subscription the link to share with another gym and who signed up with it.

---

## 8. API outline

All under `/api/v1`. Staff routes take the gym from the token. The money routes — add member with a sale, sell or renew, collect, refund, approve an app payment, record an expense, pay us — take an `Idempotency-Key` header (§11).

```
Auth
  POST /auth/register-gym            gym + owner + first branch + calendar choice, starts a trial
  POST /auth/login                   staff
  POST /auth/refresh | /auth/logout
  POST /auth/password-reset          forgot password: a code to that email or phone,
                                     if it has an account (the same answer either way)
  POST /auth/password-reset/confirm  the code and a new password; signs out every device
  POST /auth/login/two-step          the authenticator code (or a recovery code) after
                                     a password that returned a two-step token
  GET  /auth/two-step                on or off, required, recovery codes left
  POST /auth/two-step/setup | enable | recovery-codes | disable
                                     your own; setup, new codes and off need the password
  GET  /auth/sessions                your signed-in devices, this one marked
  POST /auth/sessions/{id}/sign-out | /auth/sessions/sign-out-others
  GET  /auth/push?endpoint=          notifications on this browser, and which kinds (§18.6)
  POST /auth/push | /auth/push/resume | /auth/push/off
  PUT  /auth/me/notifications        the kinds turned off
  POST /m/{slug}/otp/request         member: send code by SMS or email; unknown → 404 wording in §5.5
  POST /m/{slug}/otp/verify          member: returns session + QR secret, or the list of
                                     members on that phone to choose from
  POST /m/{slug}/desk-sign-in        member: the desk's one-time QR instead of a code (§18.4)

Setup
  GET|PATCH  /gym
  PATCH      /gym/security            require two-step sign-in for all staff (owner only)
  CRUD       /branches  /staff  /plans  /reminder-rules  /devices
  POST       /staff/{id}/password | /staff/{id}/two-step/reset | /staff/{id}/sign-out
  POST       /gym/logo

Members
  GET|POST   /members                 search, filter, paginate
  GET|PATCH  /members/{id}
  POST       /members/{id}/photo
  POST       /members/{id}/card/reissue
  POST       /members/{id}/erase      at their request, for good (owner only)
  POST       /members/import          upload → preview
  POST       /members/import/{id}/commit
  GET        /export/{members|memberships|payments|expenses|check-ins}.xlsx

Our subscription
  GET   /subscription                plan, days left, SMS balance
  POST  /subscription/payment        transaction ID for us to verify

Memberships & money
  POST  /members/{id}/memberships     new or renewal (+ optional payment; with_member_ids for a family plan, §19.1)
  GET   /membership-groups/{id}       a family or couple plan: everyone on it, the payer first
  POST  /membership-groups/{id}/members   someone joins it, to the payer's end date
  POST  /memberships/{id}/freeze
  POST  /memberships/{id}/cancel
  PATCH /memberships/{id}             edit dates, price, discount, plan, branch (§5.6)
  POST  /memberships/{id}/extend      N days + reason
  POST  /memberships/extend-all       whole gym or one branch, N days + reason
  DELETE /memberships/{id}            only while it has no check-ins
  GET   /memberships/{id}/history
  POST  /payments                     collect, incl. part payment of dues and refunds;
                                      `membership_id` or `pt_package_id` (§18.3)
  PATCH /payments/{id}
  POST  /payments/{id}/void           owner only by default
  CRUD  /payment-methods             the gym's own QR images and accounts
  GET   /payment-requests?status=pending
  POST  /payment-requests/{id}/approve
  POST  /payment-requests/{id}/reject
  GET   /freeze-requests?status=pending   GET /freeze-requests/count
  POST  /freeze-requests/{id}/approve   POST /freeze-requests/{id}/reject      (§16.3, 8.6)
  GET   /payments/{id}/receipt        printable
  POST  /payments/{id}/receipt-link   a signed link to the PDF, 30 days (§16.3, 8.4)
  POST  /m/me/payments/{id}/receipt-link   the member's own
  GET   /receipts/{id}.pdf?exp=&sig=  public: the signature is the permission
  GET   /expenses?month=&category=    a month of the gym's calendar, with totals (§18.1)
  POST  /expenses
  PATCH /expenses/{id}
  POST  /expenses/{id}/void

Personal training (§18.3)
  GET   /pt/plans?include_hidden=     POST /pt/plans   PATCH /pt/plans/{id}
  GET   /pt/trainers                  staff who train members, and the owner
  GET   /pt/clients                   the caller's own, still to train (Train members)
  GET   /pt/packages?trainer_id=      everyone's, still to train (Sell personal training)
  GET   /members/{id}/pt              every package, with sessions and payments
  POST  /members/{id}/pt              sell (+ optional payment), Idempotency-Key
  PATCH /pt/packages/{id}             trainer, dates
  POST  /pt/packages/{id}/cancel      reason, optional refund
  POST  /pt/packages/{id}/sessions    record one, Idempotency-Key
  POST  /pt/sessions/{id}/void        reason

Classes (§19.4)
  GET   /class-types  POST /class-types  PATCH /class-types/{id}
  GET   /class-slots?branch_id=  POST /class-slots  PATCH /class-slots/{id}   the weekly timetable
  GET   /class-instructors
  GET   /classes?from=&days=&branch_id=  GET /classes/mine (an instructor's own)
  POST  /classes  GET /classes/{id}  PATCH /classes/{id}  POST /classes/{id}/cancel
  POST  /classes/{id}/bookings        book a member at the desk (Idempotency-Key)
  POST  /class-bookings/{id}/cancel   POST /class-bookings/{id}/attended
  GET   /members/{id}/classes         their bookings and no-shows
  PATCH /gym/class-rules              booking opens, closes, late cancels, no-shows
  GET   /m/classes?from=  POST /m/classes/{id}/book  POST /m/class-bookings/{id}/cancel

Progress (§19.5)
  GET   /members/{id}/progress        checks, height, and photos shared with the caller if they train them
  POST  /members/{id}/progress        a check (Idempotency-Key)   PUT /members/{id}/progress/height
  PATCH /progress/{id}  DELETE /progress/{id}   only what staff recorded
  GET   /m/progress  POST /m/progress  PATCH|DELETE /m/progress/{id}  PUT /m/progress/height
  POST  /m/progress/photos            multipart: file, pose; shrunk, location stripped
  PATCH /m/progress/photos/{id}       {shared}   DELETE /m/progress/photos/{id}

Check-in
  POST  /check-ins/scan               from kiosk (device token) or staff
  POST  /check-ins/manual
  GET   /check-ins

The kiosk offline (§19.2), with its device token
  GET   /kiosk/roster                 who could come, a letter a day for 14 days
  POST  /kiosk/scans                  what it decided with no internet, recorded as decided

Door readers (§18.2, docs/READERS.md)
  POST  /devices/readers              add one: brand, branch, serial
  GET   /iclock/cdata  POST /iclock/cdata  GET /iclock/getrequest  POST /iclock/devicecmd
                                      a ZKTeco reader over ADMS, known by its serial
  GET   /kiosk/reader/commands  POST /kiosk/reader/results  POST /kiosk/reader/events
                                      a Hikvision reader's bridge, with its device token

Lists & reports
  GET   /dashboard/today
  GET   /lists/follow-up                         ending today / this week, lapsed, owing (and
                                                 personal training owing), not visiting
  GET   /members?not_visiting=true
  CRUD  /leads   POST /leads/{id}/trial   GET /leads/phone-check   GET /leads/report      (§16.4)
  POST  /members  takes `lead_id` (Convert) and `referred_by_id`
  GET   /m/{slug}/join   POST /m/{slug}/join      public, only while the gym has the join form on
  GET   /reports/monthly?month=2083-06           with personal training's figures (§18.3)

Messages
  CRUD  /notices
  POST  /members/{id}/sms             one-off reminder
  GET   /members/{id}/message?purpose=   the gym's wording filled in, for WhatsApp from
                                         the desk's own phone; sends nothing (§18.5)
  GET   /sms                          log + credit balance

Member app
  GET   /m/me   /m/me/payments   /m/me/visits   /m/notices
  GET   /m/me/push?endpoint=   POST /m/me/push   POST /m/me/push/off      (§16.3, 8.3)
  PATCH /m/me   POST /m/me/photo   POST /m/me/email   POST /m/me/email/confirm   (8.5)
  GET   /m/plans   /m/payment-methods
  POST  /m/payment-requests          plan, method, transaction ID, screenshot
  GET   /m/freeze-requests/latest   POST /m/freeze-requests   POST /m/freeze-requests/{id}/withdraw

Member access (staff)
  PATCH /members/{id}/access          app access on/off
  POST  /members/{id}/resend-welcome
  POST  /members/{id}/sign-in-link    the desk's QR: a link with a one-time token (§18.4)
  POST  /members/{id}/sign-out-all

Live updates (Server-Sent Events; ids only, the screen reloads)
  GET   /live                         staff: check-ins, members, payment requests
                                      — filtered by permission and branch — and
                                      staff changes (accounts, two-step sign-in),
                                      to everyone in the gym, so screens re-read /auth/me
  GET   /m/live                       a member: their own check-ins, membership,
                                      payments and requests

Platform admin
  GET   /admin/summary                     the numbers (§16.5, 10.1)
  GET   /admin/gyms                        with health and setup
  CRUD  /admin/changelog   GET /changelog   POST /changelog/seen   (10.4)
  GET   /admin/gym-referrals   POST /admin/gym-referrals/{id}/reward | reject   (10.5)
  GET   /subscription/referrals            the owner's link and who signed up
  GET   /admin/subscription-payments?status=pending
  POST  /admin/gyms/{id}/subscription
  POST  /admin/gyms/{id}/sms-credits
  POST  /admin/gyms/{id}/suspend
  POST  /admin/gyms/{id}/owner-password | owner-two-step
```

---

## 9. Background work (worker)

| Job | When | What |
|---|---|---|
| Automations | Daily 09:00 Nepal time | For each enabled rule: **expiry / lapsed** — members whose **chain of memberships** ends that many days away (or past), so anyone who has already renewed is never reminded; **dues** — memberships sold that many days ago still owing; **not visiting** — active members with no visit in that many days; **birthday** — current members born on the day; **pt_ending** — a member's personal training ends that many days away (or past), from their last package, a pack used up early ending on the day of its last session; **pt_dues** — personal training sold that many days ago still owing (§18.3). One SMS each, never twice for the same `dedupe_key`. A missed day is caught up for up to 2 days; a member already away longer than that when a rule is switched on isn't messaged |
| Send push | Continuously | Messages to members (automations, notices, payment answers, renewals) go by push to members with a live subscription, SMS to the rest (or both, with *Also send SMS*). Each of the member's phones is tried; 404/410 revokes it; if none takes it the SMS is sent instead; a failing push service is retried 3 times, then SMS |
| Send SMS | Continuously | Take queued SMS, check the gym's credit, send, record result, retry failures 3 times with backoff |
| OTP | Immediately on request | Sent directly, not queued behind reminders |
| Daily summary *(optional)* | 20:00 | SMS to owner: "Today: 42 visits, Rs 18,500 collected, 6 expiring this week" — a feature owners notice |
| Setup nudge | 10:30 | On day 3 and day 10 of a trial, an SMS to owners who haven't finished the setup checklist (and haven't put it away): how many of the 6 steps are done, and the next one. On us (§16.5, 10.2) |
| Cleanup | Daily | Expired OTPs and sessions, old jobs |

---

## 10. Nepal-specific details

- **Dates:** always stored in AD; shown and counted per the gym's choice (§5.1). Gyms that show BS can also *enter* dates in BS (year, month, day of the BS calendar). Python: `nepali-datetime`. Frontend: a BS converter package, with a date picker in AD or BS to match the gym. Report months follow the gym's calendar.
- **Time zone:** Asia/Kathmandu (+05:45) for every "today", reminder time and report boundary.
- **Money:** Nepali grouping — Rs 1,00,000, not 100,000.
- **SMS wording:** the welcome and "active until" SMS are gym settings (`welcome_sms`, `membership_sms`), editable with the reminder rules. The defaults stay within one SMS even with dates shown in AD and BS. New gyms start with 50 trial SMS credits (`TRIAL_SMS_CREDITS`).
- **Language:** **English only at launch** — staff dashboard, member app and SMS. Every piece of on-screen text still goes through translation files from day one, so adding Nepali later is writing translations, not rewriting screens. Gyms can already edit their own SMS wording, including in Nepali if they choose; Nepali SMS uses Unicode, which fits **70 characters per SMS instead of 160**, so the template editor shows the SMS count before saving.
- **SMS sender name:** gyms want their own name as the sender. Registering a sender ID with the gateway and operators takes time — apply early; until approved, messages go from the gateway's default sender.
- **Phone numbers:** normalised to `98XXXXXXXX` / `97XXXXXXXX`, validated as Nepali mobile numbers. `+977`, `977`, `00977`, spaces and hyphens are accepted and stripped.
- **Gym addresses (slugs):** 3–40 lowercase letters, digits and single hyphens. Our own top-level routes (`staff`, `kiosk`, `admin`, `api`, `signup`, …) are reserved in `backend/app/core/slugs.py`; a new top-level route must be added there first.
- **Receipts are payment receipts, not VAT invoices.** Tax-invoice billing software needs its own approval in Nepal; out of scope, and the receipt says so.

---

## 11. Security

- Staff passwords with bcrypt; short-lived access token (15 minutes, kept only in the page's memory), refresh token in an httpOnly `SameSite=Strict` cookie scoped to `/api/v1/auth`. The refresh token rotates on every use; the token it replaced still works for 30 seconds so two tabs refreshing together don't sign each other out, and never after. The browser sends refreshes with `keepalive`, so a rotated cookie still lands when the page navigates away mid-request (otherwise the next load, after the 30 seconds, signs the person out). Only token hashes are stored.
- The browser only talks to the Next.js server, which forwards `/api/*` to FastAPI. Everything is same-origin: the cookie is first-party and there is no CORS.
- Every request re-reads the staff account, its session, permissions and branches from the database, which is what makes "takes effect immediately" (§2.1) true.
- API errors carry a stable `code` next to the English `detail`; the frontend translates by code, so Nepali never means parsing English.
- Staff sign-in: 5 wrong passwords for one email or phone within 15 minutes and it must wait (a successful sign-in starts the count again); 20 from one IP and that address must wait. Unknown accounts are counted and answered the same way, tries refused by a limit don't count, and a lockout goes to the gym's activity log. Settings `LOGIN_MAX_FAILURES`, `LOGIN_MAX_FAILURES_PER_IP`, `LOGIN_WINDOW_MINUTES`.
- Forgot password: a 6-digit code to the email or phone typed, valid 10 minutes, 5 tries, with the OTP limits below. Every request gets the same answer, so it never shows who has an account; disabled accounts get no code. By SMS it's on us, and the SMS log keeps "Password reset code (hidden)". Platform admins reset by email. A new password signs out every device and starts the sign-in count again.
- Two-step sign-in: a 6-digit code from an authenticator app (TOTP, RFC 6238) after the password. Required for platform admins; optional for gym staff unless the owner requires it for the whole gym (only after turning on their own). An account that must use it and hasn't can sign in, but every route except setting it up answers 403 `two_step_setup_required`. The secret is never stored: it is HMAC(`TOTP_KEY`, account and a random nonce), so the database alone can't produce codes. A code works once; wrong codes count against the sign-in limit; ten single-use recovery codes cover a lost phone. Turning it on or off and new recovery codes need the password. The owner (or a manager, for other staff) resets a colleague's; we reset an owner's from `/admin`; `scripts.create_platform_admin` resets an admin's.
- Terms and privacy: `/terms` and `/privacy` (text in `frontend/src/i18n/legal.en.ts`, a lawyer to review before the first gym pays), accepted at gym sign-up and recorded with their version (`app/core/legal.py`). The gym controls its members' data and we process it for the gym (Individual Privacy Act 2075). **Erase member** (owner only, the member's name typed to confirm): name, phone, email, gender, birthday, address, emergency contact, notes and photo removed; app sessions deleted, QR and card revoked; SMS bodies and numbers, sign-in codes, payment screenshots, the before/after values in their History and their rows in imported registers removed (a phone or email still used by a family member at the gym is left alone). Memberships, payments and check-ins stay as "Erased member". An erased member can't be edited, restored or messaged.
- Security headers: every page gets a Content-Security-Policy with a fresh nonce (`frontend/src/proxy.ts`, `src/lib/csp.ts`), so only Next.js's own scripts run: injected HTML can't run script (no `'unsafe-inline'` for scripts; inline styles are allowed, since server-rendered `style=` attributes can't carry a nonce). Everything loads from our own origin; nothing may frame us (`frame-ancestors 'none'`, and `X-Frame-Options: DENY` from Caddy). Pages are therefore rendered per request. API responses get `default-src 'none'`. Every e2e test fails on any CSP violation (`frontend/e2e/fixtures.ts`).
- No double payments: the money routes take an `Idempotency-Key` header, which the browser keeps for as long as it is sending the same thing. The answer is saved with the payment, in one transaction: the same key and body again gets that answer back (`Idempotent-Replayed: true`) and changes nothing; the same key with a different body is 409; a repeat arriving while the first is still running waits for it; a failed request saves nothing, so it can be tried again. Keys are per gym and kept a day.
- Signed-in devices: My account lists every device signed in to the account (browser, IP, last used) and signs out one or all the others; the owner (or a manager, for other staff) signs a colleague out everywhere from Staff. Another account's device is not found (404). Signed-out screens find out live and go to sign-in, and a signed-out device gets no more notifications (§18.6).
- Master sign-in code: while no SMS gateway is set up (§15) sign-in codes reach only the log, so `MASTER_OTP` (6 digits, hard to guess, set in the environment) also signs a member in. Only after a code was asked for (the number must be registered, the limits apply), never for staff password resets, and every use is in the activity log (`member.signed_in_with_master_code`). The app refuses to start with it once `SMS_PROVIDER` is a real gateway.
- OTP: 6 digits, valid 5 minutes, 5 attempts, max 3 requests per phone per 15 minutes and a per-IP limit — each OTP costs us an SMS (they're never charged to the gym's credits, §5.7).
- Signing in at the desk (§18.4): the QR is the gym's address with a random token after `#desk=`. A fragment never leaves the browser, so no server or log sees it, and the member app takes it out of the address at once. Only its HMAC is stored; it works once, for 5 minutes, only the newest for a member, only at its own gym, and only while the member's app access is on. Making it needs *Turn app access on/off*; making and using it both go to the activity log.
- A sign-in code is never left readable: the SMS log keeps "Sign-in code (hidden)", since staff with the SMS permission can read the log. For end-to-end tests `OTP_TEST_CODE` fixes the code; the app refuses to start with it outside local and test environments.
- Member tokens are a separate type from staff tokens; neither is accepted in place of the other. Kiosks authenticate with a device token (`X-Device-Token`), stored hashed, and can only reach `/kiosk/*`.
- Turning app access off, changing a member's phone or email, "Sign out all devices" and "Reissue QR" all revoke the member's sessions at once.
- Members only ever see their own records; checked in every `/m/` route.
- Tenant isolation test (§3) plus a permission test for every permission in §2.1: without it the action returns 403, and a staff member cannot grant a permission they don't hold.
- Every money action, check-in override, staff change and settings change goes to `activity_log`.
- Member photos served through signed, expiring URLs, not public links.
- Backups (`deploy/backup`, `docs/DEPLOY.md` §4, §8): the database archives every WAL segment to R2 with pgBackRest, at least once a minute, and takes a base backup nightly (full on Saturday); any moment of the last 7–14 days can be restored, so a lost server loses about a minute. `restore-to-time.sh` restores a moment into a scratch copy to look at; `restore-live.sh` puts the live database back (or rebuilds a new server with `latest`). Both were tested end to end against S3 over TLS. Plus the daily `pg_dump`, kept 30 days. Restores tested once more on the real server before the first real gym goes live.

---

## 12. Build order

Estimates are for one developer working with Claude, full time. Each milestone ends with something that can be shown to gym owners.

| # | Milestone | Contents | Estimate | Result |
|---|---|---|---|---|
| **M0** | Foundations | Repo, Docker Compose, CI, database, migrations, staff auth, permission checks, tenancy helper and isolation test, gym sign-up with calendar choice | 3–4 days | You can sign up a gym and log in |
| **M1** | Members & money | Branches, staff accounts with permission checklist, plans (four seeded, AD or BS month counting per gym), members, add-and-pay flow, renewals, part payments and dues, receipts, payment methods, full membership editing with history, extend everyone, member search | 2 weeks | **Demo to gym owners from here** |
| **M2** | Expiry & SMS | Expiring list, SMS provider interface with `console` (prints to log) plus ready Sparrow and Aakash adapters — choosing one later is a setting, not code, welcome SMS, reminder rules and worker, SMS log and credits, notices | 1 week | Reminders actually go out |
| **M3** | Member app & QR | Member sign-in by SMS or email code, app access controls, **renew and pay from the app + payment requests**, PWA with per-gym manifest, member QR (rotating), printed cards, gym QR poster, kiosk, scan rules, manual check-in, attendance | 2 weeks | Full door check-in and app renewals |
| **M4** | Launch-ready | Today dashboard, monthly reports, Excel import and export, trial/lapse rules (§5.7), AD/BS dates per the gym's choice everywhere, platform admin with editable pricing, daily owner summary | 1 week | Ready for a pilot |
| **M5** | Pilot | Deploy, onboard 2–3 pilot gyms, import their registers, fix what they hit | 1–2 weeks | First paying gyms |
| **M6** | Hardening | Staff sign-in limits, forgot password, two-step sign-in, signed-in devices, no double payments, security headers, continuous backups, terms, privacy and erasing a member (§16.1) | 1 week | Safe to charge gyms |
| **M7** | Staff UI | Design-system additions, sidebar and phone navigation, search from any screen, a Today that lists what to do, member profile tabs, members table, settings pages, reports with charts (§16.2) | 2 weeks | A faster desk; the screens M8–M10 build on |
| **M8** | Keep members | Not-visiting list, automations (dues, no visits, birthday, win-back), push notifications, PDF receipts to share, member app polish, freeze requests (§16.3) | 1.5 weeks | Fewer lapsed members, smaller SMS bills |
| **M9** | Win members | Enquiries and trials, day passes and visit packs, off-peak plans enforced at the door, join form, referrals (§16.4) | 1.5 weeks | Walk-ins followed through to joining |
| **M10** | Our business | Admin numbers and gym health, onboarding nudges, support link, what's new, gym referrals (§16.5) | 1 week | We see which gyms will pay and which will leave |
| **M11** | Nepali | Nepali for the staff dashboard, member app and SMS (§16.6) | 1 week + translation | Gyms and members can work in Nepali |
| **M12** | Member phone app | Expo / React Native app for members on Android and iPhone: live updates over WebSocket, no double taps, offline QR, native notifications; shared code with the web app (§17) | 3 weeks | Members install a real app; published to the stores afterwards |
| **M13** | Expenses | What the gym spends, by category; spent and profit on Reports; export (§18.1) | 2–3 days | Owners see profit, not only income |
| **M14** | Door readers | Fingerprint and face readers, ZKTeco / eSSL or Hikvision, chosen per reader: members added to the reader and removed from it as memberships start and end; its scans become check-ins (§18.2) | ~2 weeks per brand + a reader of each to test with | Expired members stopped at a door that unlocks by itself |
| **M15** | Personal training | Monthly PT and packs of sessions, trainers' own screens (§18.3) | ~2 weeks | PT sold and tracked at the desk |
| **M16** | Family and couple plans | One sale for several people, one payer, each with their own membership and QR; the door applies the group's dues (§19.1) | ~1.5 weeks | Couples and families sold as gyms sell them |
| **M17** | Offline kiosk | A roster on the kiosk, the door rules in shared code, an Ed25519 member QR (`gb2`), offline scans sent when back online (§19.2) | ~1.5 weeks | The door keeps working when the internet drops |
| **M18** | WhatsApp messages | Meta's Cloud API between push and SMS for utility messages, approved templates, members agreeing, message credits (§19.3) | ~1 week + Meta's approvals | Reminders members read, often for less than a Nepali SMS |
| **M19** | Classes | Timetable, booking with places and a waitlist, instructors' rosters, classes in plans (§19.4) | ~2.5 weeks | Classes booked from the app, places counted |
| **M20** | Progress tracking | Weight, measurements and private photos, charts in the app and on the profile (§19.5) | ~1.5 weeks | A reason to open the app between renewals |

**Progress**

| # | Status |
|---|---|
| M0 | Done 2026-09-19 |
| M1 | Done 2026-09-19 |
| M2 | Done 2026-09-19 |
| M3 | Done 2026-09-19 |
| M4 | Done 2026-09-20 |
| M5 | Ready to deploy 2026-09-20: production stack (Caddy, R2 storage, nightly backups with restore, Sentry) verified locally; runbook in `docs/DEPLOY.md`, onboarding checklist in `docs/PILOT.md`. Waiting on: the server, the domain's DNS, the R2 buckets, an SMS gateway account (its adapter then tested live), and the pilot gyms |
| M6 | Done 2026-10-17: sign-in limits, forgot password, two-step sign-in, signed-in devices, idempotent money routes, CSP and frame headers, continuous WAL archiving with point-in-time restore (tested against S3), terms, privacy and erasing a member; also a master sign-in code while there is no SMS gateway (§11). Before charging: a lawyer reads `/terms` and `/privacy`, `TOTP_KEY` set in `.env.prod`, and the restores tested once on the real server (`docs/DEPLOY.md` §4) |
| M7 | Done 2026-10-17: sidebar and phone tab bar with a More sheet, search from any screen (Ctrl/⌘K or /), a Today with quick actions, to-do and setup checklist, member profile with tabs and a visits calendar, a sortable members table with bulk SMS, settings split into pages, Extend everyone with a preview and typed confirm, photo at the desk, charts on Reports and Attendance; toasts, confirm dialogs and loading skeletons throughout, text contrast to WCAG AA |
| M8 | Done 2026-10-17: Follow up with a *not visiting* tab (and owe money), automations (win-back, dues, not visiting, birthday) beside expiry reminders, push notifications to the member app first and SMS only where push can't reach, receipts as PDF to download and share by link, the member app's renew steps and plan savings, install prompt, *how busy now* and their own photo, email (confirmed by a code) and emergency contact, and freeze requests from the app. Before the pilot: `make vapid` and `PUSH_PROVIDER=webpush` in `.env.prod` (`docs/DEPLOY.md` §5), and check a notification on a real Android phone and an installed iPhone app |
| M9 | Done 2026-10-17: enquiries (board, list, report by source, follow-ups on Today, convert to member), trial visits, visit packs and day passes counted at the door, off-peak plans enforced at the door, the join form behind the gym QR (off by default), and referrals with the top referrers. New permission **Enquiries**, in the *Front desk* starting point |
| M10 | Done 2026-10-17: the /admin numbers and each gym's health and setup, setup nudges by SMS on trial days 3 and 10, Help (WhatsApp / Viber and guides), What's new with an unread dot, and gym referrals with a free month each. Before launch: `SUPPORT_WHATSAPP` in `.env.prod` |
| M11 | Done 2026-10-17, **waiting on a native speaker's review**: `ne.json` with every string (a test keeps its keys and {placeholders} in step with `en.json`) and Nepali help guides; a language for each staff account and each member, the gym's as the default, chosen at sign-up and in Settings → Gym; English / नेपाली on every sign-in screen, kept in a cookie; Noto Sans Devanagari through `next/font`; Nepali month names, रु, and Nepali or Western digits (a gym setting); SMS wording seeded in the gym's language, and wording the gym never edited follows a change of language. The server renders English and the browser renders Nepali, so one request's language never leaks into another's. The legal pages and the receipt PDF stay English until a lawyer and the review sign them off |
| M12 | Done (§17): 12.1 done 2026-10-17 — `shared/` holds the strings, QR, dates, money, access hours, plan value and member API types; the web app re-exports them; Docker images build with `shared/` beside `frontend/`. 12.2 done 2026-10-17 — app sessions (refresh token in the body), `/m/ws`, notice events, idempotency keys on member actions, one code per 30 seconds, Expo push subscriptions and provider, `Date` on every response (migration 0019). 12.3–12.8 done 2026-10-18 — `mobile/` (Expo SDK 58): every screen of 17.5 but *signed-in devices*, checked on the iPhone simulator and an Android emulator: the QR it draws passes the door's check, offline too; three taps on *I've paid* made one request; a notice and an approval arrived with no tap; Nepali throughout. Jest covers double taps, the socket, the API client and links. Push needs `EAS_PROJECT_ID` (mobile/README.md) and is untested until then. 12.9 done 2026-10-18 — 34 Jest tests, a lint rule that refuses API calls from a control without `useAction`, eight Maestro flows (`mobile/e2e/`, `make e2e-mobile`, on a fresh gym from `make seed-app`) passing on the iPhone simulator in Expo Go and on the Android emulator with the `.apk`, `make apk` (60 MB, 64- and 32-bit ARM, debug-signed, built on the Mac), the GymBhai icon, and `docs/MOBILE.md`: running, tests, sending the `.apk` to Android testers, and Expo Go for iPhone testers. Push set up 2026-10-18 (Expo project `@mero-gym/mero-gym`, Firebase `gymbhai-69df8`, FCM V1 key in Expo) and working end to end on the Play Store emulator: *Turn on*, a notice from the desk arrives as a notification, tapping it opens Notices. **Waiting on:** a real Android phone, real testers; iPhone push at publishing |
| M13 | Done 2026-10-19: expenses by category in the gym's own months, with *Same again* and void with a reason; spent, profit and spent by category on Reports, and money in and out on its chart; `expenses.xlsx`; *Add an expense* in search; *Record expenses* and *Edit and void expenses* in an *Expenses* area of the staff form; an `expense` live event and a query-count test. Also fixed: the staff form never showed the *Enquiries* permission (its area was missing from the form's list); it now shows any area it doesn't know, at the end |
| Pilot helpers | Done: signing in at the desk with a QR (§18.4), WhatsApp buttons (§18.5) and notifications for staff (§18.6) on 2026-10-19; a demo gym (§18.7, `make seed-demo`) on 2026-10-20. **Waiting on** real phones: staff and member web notifications on an Android phone and an iPhone's Home Screen, by the checks in `docs/PUSH.md` (a tunnel to the Mac gives the `https://` they need) |
| M14 | Built before a reader, 2026-10-20 (§18.2, docs/READERS.md): readers in Settings → Door scanners, members put on them with their reader number, scans as check-ins under the same rules; ZKTeco over ADMS, Hikvision through a bridge at the gym (`bridge/`), each to its maker's published protocol and tested against a simulated reader. **Waiting on** the pilot gyms' reader models and one reader of each brand, to confirm the protocols and, for ZKTeco, how a reader refuses an expired member |
| M15 | Done 2026-10-19 (§18.3): PT plans in Settings, monthly or a pack of sessions; *Train members* and *Sell personal training*, and a *Trainer* starting point; selling from the member's profile with a part payment; sessions recorded by the trainer or the desk, voided with a reason; PT payments as ordinary payments with their own dues and receipts; *My clients* and *All* in a Personal training screen; the member's Home on the web and the phone app; a `pt` live event; migration 0022. 2026-10-20: PT reminders (two automations), PT owing in Follow up, PT figures on Reports; migration 0025 |
| M16 | Done 2026-10-20 (§19.1): plans for up to 6 people; one sale makes everyone's membership, the money on the payer's; the door applies the payer's dues to everyone; adding someone to a free place, removing someone, the payer's plan change and cancel carrying everyone; expiry and win-back to the payer only, the others told by push; the receipt lists everyone; the member's Home and Renew on the web and the phone app, the payer renewing for everyone; migration 0026 |
| M17 | Done 2026-10-20 (§19.2): the kiosk keeps a roster of 14 days of the door's own decisions and decides by itself for the gym's offline days, sending the scans when back; a new member QR, gb2, signed with Ed25519, which a kiosk checks with public keys alone; a shared table of door cases both sides are tested on; the kiosk's own service worker and manifest; quiet kiosks on Today; migration 0027. **Waiting on** a real tablet at the door with its Wi-Fi switched off, and the phone app's next build for gb2 (older builds keep showing gb1, which works online) |
| M19 | Done 2026-10-20 (§19.4): class types and a weekly timetable that makes each class 4 weeks ahead; booking from the app and at the desk, places counted under a lock, a waitlist that moves up by itself with a push; plans that include all, some or no classes; booking windows, late cancels and an optional pause after no-shows; the instructor's roster with who came, from their tick or the door; a reminder an hour before; classes on the member's profile and on Reports; the member's Classes on the web and the phone app; three permissions in a *Classes* area; migration 0028 |
| M20 | Done 2026-10-20 (§19.5): weight, body fat and five measurements over time with BMI from a height; recorded by the member or by staff with *See and record progress*, each changing only their own; the activity log never holds the figures; photos private to the member unless shared with their trainer, not even the owner seeing them otherwise, shrunk and stripped of location; a weight chart on the profile, the web app and the phone app; erasing a member takes it all; a check-up reminder by push only, off to start; migrations 0029 and 0030 |
| M18 | Planned 2026-10-20 (§19.3): start Meta's WhatsApp verification now |

**Roughly 7–8 weeks to a pilot.** Start showing M1 to owners in week 3 — don't wait for the full build to find out what they'll pay.

---

## 13. Testing and deployment

**Testing**
- Backend: pytest — unit (dates, dues, renewal start dates, QR codes, BS conversion), integration against real Postgres (every route), regression (tenant isolation, permissions).
- Frontend: Vitest + Testing Library for components.
- End-to-end (Playwright), the one flow that must never break: *add member → take payment → member signs in → scans QR at kiosk → allowed; membership ends → scan denied.*
- CI runs all of it on every push.
- Migrations are checked (apply, match the models, roll back) in CI and with `make migration-check`, always in a scratch database: rolling back empties whatever database it runs in.

**Deployment (first gyms)**
- One VPS running Docker Compose (`docker-compose.prod.yml`), Caddy in front for HTTPS; Caddy sends `/api` straight to the API and everything else to the web app. Postgres on the same machine at first, with the off-site backups above (continuous WAL archiving to R2 plus a `backup` container for base backups and the nightly dump); move to managed Postgres when there are enough gyms to justify it. See `docs/DEPLOY.md`.
- Domain, SMS gateway account with credit, S3-compatible storage for photos and backups.
- Error tracking (Sentry free tier) and an uptime check.

---

## 14. After v1

The next milestones, M6–M11, are planned in §16 (self-service freeze requests and Nepali moved there); M13–M15, from what the pilot gyms asked for, in §18; M16–M20, from this list, in §19. After them, in rough order, driven by what pilot gyms ask for and will pay for:

1. Fingerprint and face readers at the door, including turnstiles and door locks (§4.3) — many Nepali gyms already own a ZKTeco reader, so for some this decides whether they buy. **Now M14 (§18.2)**
2. Automatic payment verification — Fonepay dynamic QR / eSewa merchant APIs confirm an app payment so it activates without staff approval; needs each gym's merchant account
3. Personal training packages and sessions, with trainer permissions and screens — assigned members, workout and diet plans. **Now M15 (§18.3)**
4. Supplement / merchandise sales at the desk — not asked for by the pilot gyms (§18)
5. Expenses (rent, salaries, electricity) so the owner sees profit, not only income. **Now M13 (§18.1)**
6. Family and couple plans — one sale covering several linked members; needs its own design, because dues and status are per membership today. **Now M16 (§19.1)**
7. Class schedule and booking. **Now M19 (§19.4)**
8. Offline kiosk — queue scans and sync when the internet returns. **Now M17 (§19.2)**
9. Progress tracking — weight, measurements, private photos, charts. **Now M20 (§19.5)**
10. WhatsApp messages alongside SMS. **Now M18 (§19.3)**
11. Branded app store app per gym — sold as an add-on; the same code as M12's GymBhai app (§17) with each gym's name and icon
12. Tax invoices from billing software approved by the Inland Revenue Department, for VAT-registered gyms — needs approval, so only if larger gyms ask

---

## 15. Decisions

All of these can be changed later.

| Topic | Decision | What the build does now |
|---|---|---|
| **Name and domain** | **GymBhai**, `gymbhai.com` | Used in every URL, the member app and the code. Register the domain (and the Facebook / Instagram names) soon — it was free on 2026-09-19 |
| **SMS gateway** | Later | Built ready: one SMS interface, `console` provider for development, Sparrow and Aakash adapters ready. Until one is chosen, members sign in with `MASTER_OTP` (§11). Choosing one is an environment setting plus the account's API key. The adapters follow the gateways' published APIs but have not been run against a live account: `python -m scripts.sms_check` reads the account's credit balance before anything is sent (docs/DEPLOY.md §5). Sparrow (checked against docs.sparrowsms.com on 2026-09-20) also whitelists the caller's IP address and queues without giving a message id, so there is no delivery report to record |
| **Pricing** | Later | Plans with us are rows edited in `/admin`, never hard-coded; the trial works without any price set |
| **Door hardware** | Fingerprint and face readers: ZKTeco / eSSL and Hikvision, the brand chosen for each reader (§18.2, M14) | v1 ships QR (kiosk, staff phone, USB scanner, manual). The check-in service accepts other sources, so fingerprint / face readers plug in without changing it (§4.3) |
| **Language** | English only at launch | All text in translation files so Nepali can be added later without redoing screens |
| **Calendar** | Each gym chooses | AD or BS for counting plans; AD, BS or both for showing dates (§5.1) |
| **Staff** | Owner decides per person | Staff accounts with ticked permissions and branches, including approving app payments (§2.1) |

---

## 16. Next: hardening, a better desk, retention (M6–M11)

*Planned 2026-10-17, after v1 (M0–M5).*

**Order.** Hardening comes first, because it has to be done before we charge a gym. The staff UI comes second, so the new screens in M8–M10 are built once, on the new navigation and components, instead of being built and then redone.

**v1's rules still apply to every step:** `gym_id` from the token, and a test proving another gym's ids return 404 for every new route. One specific permission per endpoint, with a test that it returns 403 without it. Money in paisa. Status computed from dates. Every edit in `activity_log`. Every piece of text in `en.json`.

**How steps land.** Each numbered step ends green: pytest, Vitest, lint, `make migration-check` and the e2e suite. Each one is a clean commit point. A new model and its migration always go in the same step. When a step changes how something works, §7, §8 or §11 is updated in the same step.

### 16.1 M6 — Hardening (before charging the first gym)

| # | Step | What |
|---|---|---|
| 6.1 | Staff sign-in limits | Table `login_attempts` (`identifier`, `ip`, `at`, `succeeded`). After 5 failures for one account in 15 minutes, that account waits 15 minutes. After 20 failures from one IP in 15 minutes, that IP waits. Every refusal uses the same `too_many_attempts` answer, so it never shows whether the account exists. A successful sign-in clears the account's count. Lockouts go to the activity log |
| 6.2 | Forgot password | A link on `/staff/login`. A 6-digit code is sent to the email or phone that was typed, if it belongs to an account: email is free, and SMS is on us, like member sign-in codes (§5.7). It lasts 10 minutes, allows 5 tries and has the same rate limits as the OTP. A new password signs out every other device. Table `staff_password_resets` (`staff_user_id`, `code_hash`, `expires_at`, `attempts`, `consumed_at`, `ip`) |
| 6.3 | Two-step sign-in | An authenticator app (TOTP): no SMS cost, and it works without signal. **Required for platform admins.** Optional for gym staff, and the owner can require it for everyone in the gym (in Settings → Security). 10 single-use recovery codes, stored hashed. A platform admin can reset an owner's two-step sign-in, and that is logged. The secret is never stored: it is derived from `TOTP_KEY` and a random `staff_users.totp_nonce`, which needs no encryption library and gives the same protection. Also `totp_enabled_at`, `totp_last_step` (no code works twice) and a table `staff_recovery_codes` |
| 6.4 | Signed-in devices | **My account → Devices** lists each `staff_sessions` row (browser, IP, last used), with **Sign out** for one device and **Sign out all others**. On **Staff**, the owner can sign out any staff member's devices |
| 6.5 | No double payments | Every money POST takes an `Idempotency-Key` header, which the frontend makes once per form. That covers selling or renewing, collecting, refunds, approving a payment request, and sending us a subscription payment. Table `idempotency_keys` (`gym_id`, `key`, `route`, `request_hash`, `status_code`, `response`, `created_at`), unique on `gym_id` + `key`. The same key with the same body returns the first response again; the same key with a different body gets 409. Rows are removed after 24 hours. A test sends the same sale twice and finds one membership and one payment |
| 6.6 | Security headers | `Content-Security-Policy` with script nonces from the Next.js middleware (the App Router inlines scripts), allowing `blob:`/`data:` for QR codes and photos, the storage host and Sentry. Plus `frame-ancestors 'none'`. Set in the Caddyfile, with the same policy in development so problems show up early |
| 6.7 | Continuous backups | Keep the nightly `pg_dump`, and add WAL archiving with `wal-g` to R2. Any moment in the last 7 days can be restored, so a failure loses about a minute of payments instead of a day. Restoring to a chosen time is written up in `docs/DEPLOY.md` and tested once |
| 6.8 | Terms, privacy, erasing a member | `/terms` and `/privacy` pages: we draft them, and a lawyer reviews them before the first gym pays. They are accepted at gym sign-up (`gyms.terms_accepted_at`, `terms_version`). The gym controls its members' data; we process it for the gym (Individual Privacy Act 2075). **Erase member** is for the owner only. The name becomes "Erased member". Phone, email, address, date of birth, emergency contact and notes are cleared, and the photo is deleted. Sessions, the QR and the card are revoked. Memberships, payments and check-ins stay, for the gym's accounts. The activity log records the erasure without the erased details |

### 16.2 M7 — Staff UI

**What's wrong today** (from screenshots on 2026-10-17):
- The 14 menu pills wrap onto two rows on a laptop. On a phone only four are visible, and the rest are off-screen.
- You can't find a member from any screen; the desk has to open Members first.
- Today shows eight numbers of equal weight and no to-do list. A new gym sees zeros instead of what to set up next.
- The member profile is one long page. Collect payment, Freeze and Check in are not at the top, and visits aren't shown.
- Settings is one page about 4,000 pixels long. **Extend everyone** is at the bottom, already filled in with 7.
- Deleting or archiving uses the browser's `window.confirm`. Saving shows no confirmation, and loading shows a blank page.
- Reports are numbers, with no trend over time.
- Add member has no photo, although the printed card relies on the desk checking the face (§4.2).

**7.1 Components first.** These are added to the design system, built on the tokens in `globals.css` and each tested with Vitest. Screens use them instead of making their own.

| Component | Use |
|---|---|
| Icons | `lucide-react`, the one new dependency: one stroke weight, used in the menu, buttons and empty states. It replaces the inline SVGs |
| `Sidebar`, `BottomNav` | The navigation (7.2) |
| `CommandPalette` | Search from any screen (7.3) |
| `Toast` | Confirms every save ("Payment recorded — Receipt #42"), with **Undo** wherever the action can be reversed |
| `ConfirmDialog` | Replaces every `window.confirm`. For bulk or irreversible actions (Extend everyone, Erase member, committing an import) it states the effect ("Adds 7 days to 214 memberships") and asks you to type to confirm |
| `Menu` | The **More ▾** menu of actions |
| `Tabs` | The tab is kept in the URL (`?tab=payments`), so it can be shared as a link and survives a refresh |
| `DataTable` | Sortable columns, row selection and a sticky header. On a phone it becomes the card list used today |
| `Skeleton` | Loading placeholders in the layout's shape, instead of a blank page |
| Charts | Small SVG components we build ourselves: `Sparkline`, `Bars`, `Line`, `Heatmap`. They use the tokens, work in print, and add no chart library |
| `ActionBar` | A save bar that stays visible at the bottom of long forms and shows the total on the sale form |

**7.2 Navigation.**
- On a laptop (1024px and wider), a left sidebar in four groups, still filtered by permission. The gym name, staff name and account menu sit at the top, and the sidebar can collapse to icons.
  - **Desk:** Today · Door · Members · Follow up · Payment requests (count)
  - **Money and numbers:** Payments · Reports · Attendance
  - **Grow** (from M8): Enquiries · Messages (notices, SMS log, automations)
  - **Gym:** Staff · Import / export · Settings · Subscription
- On a phone, a bottom bar: Today · Members · **Scan** · Requests · More. **More** opens a sheet with everything else.

**7.3 Search from any screen.** <kbd>Ctrl</kbd>/<kbd>⌘</kbd>+<kbd>K</kbd>, or <kbd>/</kbd>, or the search box in the sidebar. It finds members by name, phone or code through `GET /members?q=`. Each result shows the photo, status, days left and dues. Enter opens the profile, and buttons on the result do **Renew**, **Check in** or **Collect**. It also lists actions: Add member, Scan, Collect payment. If name search gets slow or misses spelling variants ("Raam"), add a `pg_trgm` index on `members.name`, but measure first.

**7.4 Today.**
- **Quick actions** at the top: Add member · Scan · Collect payment.
- A **To do** list, each row with its own button: payment requests waiting → Approve · ending today → Call / Remind · owing money → Collect · not visiting (M8) → Message.
- The numbers stay, each with a comparison ("vs yesterday", "vs the same day last month"). Next to them, a chart of today's check-ins by hour.
- A **setup checklist** for new gyms until it's done or dismissed: plans priced · payment account added · logo · a staff member invited · QR poster printed · first member. Everything except the poster is worked out from data. Opening the poster sets `gyms.settings.poster_printed_at`.

**7.5 Member profile.**
- **Header:** photo, name, code, status, days left and dues.
- **Actions:** **Renew** · **Collect payment** (when they owe) · **Check in** · **More ▾**. More holds Freeze, Send SMS, Print card, Reissue QR and card, Resend welcome, Sign out all devices, App access, Archive and Erase.
- **Tabs:**
  - Overview: current membership, details, notes
  - Memberships
  - Payments
  - **Visits**: a month calendar, with denied scans marked
  - Messages: SMS and, from M8, push
  - History

**7.6 Members list.**
- On a laptop it becomes a table: photo and name · code · phone · plan · ends on · days left · dues · **last visit**. Every column sorts.
- The filter chips show counts.
- Selecting rows offers **Send SMS** and **Export**.
- The list API returns `last_visit_at`, computed with a subquery and an index on `check_ins (gym_id, member_id, at)`, and covered by `test_query_counts`.

**7.7 Add member and Renew.**
- A photo taken with the desk's webcam or the phone's camera, uploaded straight away.
- The total and **Save** in the `ActionBar`.
- Enter moves to the next field.
- The warning for a phone that's already on file stays as it is.

**7.8 Settings.**
- Split into pages with their own menu: Gym profile · Calendar and dates · Plans · Payment accounts · Branches · Check-in rules · Door scanners · Security (6.3). Each page saves on its own and warns about unsaved changes.
- Reminders and SMS wording move to **Messages → Automations** (8.2).
- **Extend everyone** moves to **Members → More ▾**: empty by default, and its `ConfirmDialog` says how many memberships it will change.

**7.9 Reports and attendance.**
- Income by month for the last 12 months, active members over time, renewal rate, and new against lapsed members, each with the change from last month.
- Attendance gets a heatmap of check-ins by day and hour, replacing the busiest-hours list.
- Both print cleanly.

**7.10 Finish.**
- Toasts on every save, skeletons on every page, and an empty state with the next step on every list.
- `ConfirmDialog` everywhere.
- WCAG AA contrast, and every action reachable from the keyboard.
- The e2e selectors updated for the new navigation.

### 16.3 M8 — Keep members

| # | Step | What |
|---|---|---|
| 8.1 | Not visiting | Members with an active membership and no visit for N days (Settings → Check-in rules, default 14). Expiring becomes **Follow up**, with tabs: ending soon · lapsed · owe money · **not visiting**. Each tab shows the last visit, **Call** and **Send message**. Today shows the count |
| 8.2 | Automations | Reminder rules get a `trigger`: before or after expiry (today's rules), dues unpaid for N days, no visit for N days, birthday, or lapsed for N days (win-back). Same template editor with the SMS count. `reminder_log` gets a `dedupe_key` (rule + membership; or rule + member + date, for birthdays and visits), so nothing is sent twice. Only expiry rules are on by default. Lives under **Messages → Automations** |
| 8.3 | Push notifications | Web Push (VAPID keys, `pywebpush`) to the member app. After their first sign-in, the member is asked on Home: "Get reminders on this phone". On an iPhone the app must be installed first (iOS 16.4+), and the prompt explains that. Table `push_subscriptions` (`gym_id`, `member_id`, `endpoint`, `p256dh`, `auth`, `user_agent`, `last_ok_at`, `revoked_at`); a subscription the push service rejects is revoked. Every message to a member (reminder, notice, approved, rejected) is tried **by push first**. SMS goes only to members without a working subscription, or to everyone if the gym turns on "Also send SMS". Push costs nothing and uses no credits. A notice's cost preview says "180 by push, 34 by SMS (34 credits)" |
| 8.4 | Receipts to share | A PDF built on the server (fpdf2, A5, Noto Sans with Devanagari shaped by HarfBuzz, so Nepali names print right), opened from a signed link that works for 30 days without signing in: `POST /payments/{id}/receipt-link` (staff), `POST /m/me/payments/{id}/receipt-link` (the member's own), `GET /receipts/{id}.pdf?exp=&sig=`. The receipt page has **PDF** and **Share** uses the phone's share sheet (WhatsApp, Viber, Messenger); otherwise it copies a link. In the member app, Payments → **Download receipt** |
| 8.5 | Member app | **Renew:** plan cards with the price per month and "save Rs X compared with monthly", plus steps: Plan → Pay → Send proof. **Install:** an "Add to Home Screen" prompt on Android and an instructions sheet on iPhone. **How busy now:** Quiet / Normal / Busy on Home, from check-ins in the last 2 hours; the gym can hide it. **Profile:** the member can change their email, emergency contact and photo, and each change is logged |
| 8.6 | Freeze requests | The member asks from the app (dates and reason). Staff with **Freeze** approve or reject it, the same way as payment requests, with a count in the menu. Table `freeze_requests`. Moved here from §14 |

### 16.4 M9 — Win members

| # | Step | What |
|---|---|---|
| 9.1 | Enquiries | Table `leads`: `gym_id`, `branch_id`, `name`, `phone`, `email`, `source` (walk-in, phone, Facebook, Instagram, TikTok, referral, other), `plan_id` (the plan they're interested in), `status` (new → contacted → trial → joined / lost), `follow_up_on`, `lost_reason`, `assigned_to`, `member_id` once joined, and `notes`. Shown as a board by status, or a list. Follow-ups due today appear on Today. **Convert** opens Add member already filled in and links the enquiry to the new member. A report shows enquiries, trials, joins and the conversion rate by source. New permission **Enquiries** (`leads.manage`), added to §2.1 and to the *Front desk* starting point. A phone that already belongs to a member gives a warning, the same way as Add member does |
| 9.2 | Trial visit | **Trial visit today** on an enquiry marks it trial and records the date. It isn't a check-in, because an enquiry isn't a member yet |
| 9.3 | Day passes and visit packs | A day pass is just a plan with `duration_days = 1`. Visit packs add `plans.visit_limit` (null means unlimited), copied onto the membership when it's sold. The door counts allowed check-ins on that membership, and at the limit refuses with `denied_visits_used`. The member app shows "7 of 10 visits left". Status is still computed, from dates plus the count |
| 9.4 | Off-peak plans | `plans.access_hours`, a list of `{days, from, to}` in Nepal time, is copied onto the membership. Outside those hours the door refuses with `denied_hours`, and staff can override. A plan called "Morning only" is then actually enforced at the door |
| 9.5 | Join form | Optional, off by default (from §5.5): a public form behind the gym QR. It creates an enquiry, never a member, and is rate-limited per IP |
| 9.6 | Referrals | Add member and enquiries get **Referred by**, chosen with a member search. Reports list the top referrers. Rewards stay manual (Extend by N days, with a reason) |

### 16.5 M10 — Running GymBhai

| # | Step | What |
|---|---|---|
| 10.1 | Admin numbers | The `/admin` home shows monthly recurring revenue, gyms by state (trial, paying, grace, read-only, suspended), the share of trials that start paying, gyms lost each month, and SMS credits sold. For each gym: last staff sign-in, check-ins in the last 7 days and members added, with a **going quiet** flag |
| 10.2 | Onboarding nudges | `/admin` shows each gym's setup checklist (7.4). From us, on day 3 and day 10 of the trial, an SMS goes to owners who haven't finished it |
| 10.3 | Support | A **Help** button in the staff dashboard opens a WhatsApp / Viber chat with us (`SUPPORT_WHATSAPP`) and short how-to pages |
| 10.4 | What's new | Changelog entries are rows edited in `/admin`. The staff dashboard shows a dot until each staff member has read the newest one |
| 10.5 | Gym referrals | The owner shares a link. When the referred gym's first payment is approved, both gyms get a free month, which we approve in `/admin` |

### 16.6 M11 — Nepali

- `ne.json` alongside `en.json`.
- A language choice for each staff account and each member, with the gym's choice as the default.
- A Devanagari font through `next/font`, and a gym setting for Nepali or Western digits.
- Default SMS wording in Nepali (Unicode, so 70 characters per SMS; §10).
- Error codes are already translated by code (§11).
- A native speaker reviews every screen before release. *(Not done yet: the translation in `ne.json` and `help.ne.ts` is a first draft.)*

### 16.7 What the data model gains

| Table / column | Step |
|---|---|
| `login_attempts`, `staff_password_resets`, `staff_recovery_codes`, `staff_users.totp_nonce` / `totp_enabled_at` / `totp_last_step` | 6.1–6.3 |
| `idempotency_keys` | 6.5 |
| `gyms.terms_accepted_at`, `gyms.terms_version` | 6.8 |
| `reminder_rules.trigger`, `reminder_log.dedupe_key` | 8.2 |
| `push_subscriptions` | 8.3 |
| `freeze_requests` | 8.6 |
| `leads`, `members.referred_by_id` | 9.1, 9.6 |
| `plans.visit_limit` / `access_hours`, copied to `memberships` | 9.3, 9.4 |
| `check_ins.result` gains `denied_visits_used`, `denied_hours` | 9.3, 9.4 |
| `changelog_entries`, `staff_users.changelog_seen_at` | 10.4 |
| `gym_referrals` | 10.5 |

---

## 17. M12 — The member app for phones (React Native)

The installable web app (§7, M3, M8) stays. M12 adds a native app for members on Android and iPhone, built with Expo, for what a store app does better: an app people find and trust, a camera-free QR that opens in one tap, notifications that work everywhere (iPhone without "Add to Home Screen"), and live updates that never stop. Members only: staff keep the web dashboard (§16, staff notifications on the web come separately).

**One app, every gym.** One "GymBhai" app; the member chooses their gym by scanning its poster QR, typing its address, or a link from the welcome SMS, and the app takes on that gym's name, logo and colour. A branded app per gym (§14, 11) is the same code with a different name and icon, later.

**Built and tested for free; published later.** Expo and React Native are free. Android test builds (`.apk`) are made on the Mac and shared with testers; iPhone testers use Expo Go. The store accounts (Google Play $25 once, Apple $99 a year) are bought only when publishing, after M12 is done.

### 17.1 Decisions

| Area | Choice | Why |
|---|---|---|
| Framework | Expo (React Native, TypeScript), **Expo Router**; the Expo SDK pinned to a release at least two weeks old when M12 starts | File-based screens like the web app; builds without Android Studio or Xcode projects to maintain |
| Where | `mobile/` in this repo, beside `frontend/` | One repo, one CI |
| Shared code | A `shared/` workspace package, used by `frontend/` and `mobile/`: the i18n catalogs and `t()`, the member QR code (`memberQr`, `hmac`), BS/AD dates and the BS calendar table, money formatting, access hours, plan value, and the member API types | The QR, dates and every string must be identical in the web and native apps; one copy, tested once |
| Data | TanStack Query for loading and caching; its cache persisted on the phone | Screens show the last data at once, offline too, and refresh when told to (17.3) |
| Session | Access token in memory; refresh token in the phone's secure storage (`expo-secure-store`) | The web keeps its httpOnly cookie; an app has no cookie jar to rely on (17.2) |
| Live updates | **WebSocket**, always connected while the app is open (17.3) | Server-Sent Events are one-way and need a polyfill in React Native; a WebSocket is built in, and lets the app renew its token without reconnecting |
| Notifications | Expo push (free), through Firebase on Android and Apple's service on iPhone | One API for both; the server sends with the same "push first, SMS for the rest" rules as M8 (17.6) |
| Font and language | Inter and Noto Sans Devanagari bundled; English and Nepali from the shared catalogs; the gym's or member's language (§16.6), the phone's language before sign-in | Same words and rules as the web app |
| Tests | Jest and React Native Testing Library; **Maestro** flows on an Android emulator (free); the backend's pytest for everything new on the server | |

### 17.2 Server changes (`backend/`)

1. **App sessions without cookies.** `POST /m/{slug}/otp/verify` and `POST /m/auth/refresh` take `"client": "app"`: the refresh token comes back in the body instead of a cookie, and refresh takes it in the body. Rotation and reuse detection stay exactly as they are (§11). `POST /m/auth/logout` takes it in the body too. Sessions record the app and phone model, shown in staff's *signed-in devices* for the member.
2. **WebSocket `GET /api/v1/m/ws`** (17.3), on the same event hub as the SSE streams, with the same `member_filter`.
3. **Notices reach the app live.** Publishing or removing a notice publishes a `notice` event that every member of the gym (in its branches) hears; today the member stream only hears events about the member themself.
4. **No double requests from members** (17.4): the member routes that add something or move it along take an `Idempotency-Key` header, using the M6 store (`idempotency_keys.member_id` scopes a member's keys; another member's or staff's use of the same key is a 409): asking to renew (with its screenshot), withdrawing it, asking to freeze and withdrawing it, joining, and confirming an email change. The rest are idempotent by nature and need no key: the photo and profile changes set values, turning notifications on again updates the same row, and asking for an email-change code twice within 30 seconds sends one code (as in 5).
5. **"Send me a code" twice in a row sends one code.** A second request for the same number within 30 seconds answers "sent" again without a second SMS (and without using up the limit of three); the app shows a countdown before *Send again*.
6. **Native push subscriptions.** `push_subscriptions` gains `kind` (`web`, `expo`) and `expo_token`; `endpoint`, `p256dh` and `auth` become web-only. `POST /m/me/push` accepts either kind (`{"kind": "expo", "expo_token": "ExponentPushToken[…]"}`) and `/m/me/push/off` takes either the endpoint or the token. The Expo provider sends each phone its message and reads the ticket Expo answers with: `DeviceNotRegistered` revokes the subscription, as a 404/410 does for web push; anything else is retried by the worker. (A message goes to one member's few phones at a time, so batching and Expo's later receipts aren't needed yet; a gone token also fails its next send.) The app's push needs no VAPID key, so app users get push even where browsers fall back to SMS. `EXPO_ACCESS_TOKEN` is optional, needed only with Expo's enhanced push security on.
7. **Clock skew.** Every response carries the server time (`Date`); the app corrects its QR window by the difference, so a phone set a few minutes wrong still shows a code the door accepts (today the door allows one window, 30 seconds, either side).

### 17.3 Live updates over WebSocket

- **Connect:** `wss://<domain>/api/v1/m/ws`. The first message must be `{"type": "auth", "token": "<access token>"}` within 5 seconds, or the server closes with 4401. Tokens never go in the URL, so they never reach a log.
- **Then:** the server sends `{"type": "ready"}`, then events as they happen, `{"type": "member" | "payment_request" | "freeze_request" | "check_in" | "notice", ...ids}`. Events carry ids, never data: the app re-reads through the normal API, which checks permissions as always (§11, as for SSE).
- **Staying signed in:** before the access token expires the app sends a fresh one in another `auth` message on the same connection. A token that expires without one closes the socket with 4401, and the app refreshes and reconnects. A revoked session (signed out by staff, erased member) stops receiving within the token's lifetime, as today.
- **Alive:** a `ping` from the server every 25 seconds; the app answers `pong`. Nothing heard for 60 seconds: closed with 4408. A message that isn't JSON closes it with 1011. The app reconnects after any close; after 4401 it refreshes its token first.
- **Reconnecting:** after a dropped connection, the phone waking or returning online, or the app coming back to the foreground, the app reconnects with backoff (1, 2, 5, 10, 30 seconds), and on `ready` re-reads every screen it has open (it may have missed events). A slow app whose queue overflows gets `{"type": "resync"}`.
- **What updates live:** Home (days left, status, dues, *how busy*), a renewal request approved or rejected, a freeze answered, a visit appearing the moment the door lets them in, a new notice, a payment taken at the desk.
- **Through the stack:** Caddy passes WebSocket upgrades as it is, routed with the SSE streams (no compression, kept open across a config reload); the app talks to the API directly, not through the Next.js proxy. The code is `backend/app/api/routes/member_socket.py`; the route-permission walk lists sockets in `tests/routes.py` `WEBSOCKETS`, since they sign in by message rather than a dependency.
- The web member app keeps SSE for now (it works through the Next.js proxy); moving it to the same WebSocket later is a small change.

### 17.4 No double taps, no double payments

Three layers, so one tap is one action however the network behaves:

1. **On screen.** Every button that changes something goes through one hook, `useAction`, that locks **synchronously** on the first tap (a ref, not React state, which updates a frame later) and ignores more taps until the request ends. The button shows a spinner and is disabled meanwhile; forms can't submit twice from the keyboard either. A lint rule refuses `onPress` handlers that call the API without it.
2. **On the wire.** Each action gets an `Idempotency-Key` when it starts. If the network fails and the app retries, or the member taps again after an error, the same key goes again; a new key is made only after success, or when what they're sending changes.
3. **On the server.** The keys (17.2, 4) mean a repeated request returns the first answer and changes nothing, even when two arrive at once. Rules that already exist stay: one waiting renewal and one waiting freeze per member, a transaction ID used once per gym, the limits on codes.

Tested at each layer: a test taps every action button twice within 10 ms and expects one request; backend tests send each member action twice with one key, at once, and expect one row; a Maestro flow double-taps *I've paid* on a slow network.

### 17.5 Screens

Everything the member web app does (§7), the same words:

| Screen | Native details |
|---|---|
| **Choose your gym** | Scan the gym's poster QR with the camera, type its address, or open from the welcome SMS link (deep link `gymbhai://<gym>`, and `https://<domain>/<gym>` once published). Remembers the gym; a member of two gyms can switch |
| **Sign in** | Mobile number or email, then the code; the code is read from the SMS on Android where the phone allows. *Who are you?* for a shared phone. Or *Scan the QR at the desk* (§18.4); the poster scan on *Choose your gym* signs in too when it finds a desk QR |
| **Home** | Days left ring, *visits left* for packs, plan hours, dues, *how busy now*, latest notice; **the QR** (17.1), full brightness while shown, works with no signal; *Ask to freeze* |
| **Renew** | Plan → Pay → Send proof; the gym's payment QR can be saved to the gallery to pay in the wallet app; screenshot from the gallery or camera |
| **Payments** | Payments and requests; receipts open as PDF and share through the phone's share sheet |
| **Visits** | The month's calendar, live |
| **Freeze** | From a day and for how many days, by stepping, not the phone's date picker: that only knows AD, and many gyms show BS |
| **Notices** | Live; a notification opens the notice |
| **Me** | Photo, email (code to the new address), emergency contact, language, notifications, notices, switch gym, sign out. *Signed-in devices* waits for a member API that lists and ends their own sessions |
| **Join** | The gym's join form (§16.4, 9.5), when it has it on |
| Offline | A banner (no answer from the server counts, whatever the phone's Wi-Fi says); the QR keeps working, drawn at the server's time saved from the last answer; actions wait for the connection and say so, rather than failing |

Accessibility: every control labelled for screen readers, touch targets at least 44 points, text that grows with the phone's font size.

### 17.6 Notifications

- After the first sign-in, Home offers *Get reminders on this phone*; the phone's permission is asked only when they tap it.
- The token is registered as an `expo` subscription (17.2, 6); everything M8 sends by push (reminders, notices, payment and freeze answers, renewals) reaches the app with no change to the rules, and SMS goes only where no push can.
- Tapping a notification opens the right screen (renew, payments, notices, freeze).
- Expo Go on Android has no push (removed in SDK 53): the app runs there with notifications off; the `.apk` and development builds have them. Push also needs the Expo project id (`EAS_PROJECT_ID`, mobile/README.md).
- Android needs a free Firebase project for its credentials. iPhone push needs Apple's push key, which comes with the paid Apple account, so iPhone notifications are tested when publishing; Android notifications are tested on `.apk` builds before then.

### 17.7 Steps

| # | Step | Estimate |
|---|---|---|
| 12.1 | `shared/` package: move the catalogs, QR, dates, money, access hours, plan value and API types out of `frontend/`; npm workspaces; the web app imports from it; its tests run in CI | 1 day |
| 12.2 | Server: app sessions (17.2, 1), the WebSocket (17.3) with tests, notice events, idempotency on member routes, the code cooldown, Expo push subscriptions and provider, the server time | 3 days |
| 12.3 | App skeleton: Expo Router, theme from the gym, fonts, `t()` and language, the API client (refresh, idempotency keys, retries), `useAction`, the WebSocket client, the persisted cache, offline banner | 2 days |
| 12.4 | Choose your gym, sign in, *Who are you?*, sign out | 1 day |
| 12.5 | Home and the QR (offline, brightness, clock skew) | 1 day |
| 12.6 | Renew and pay, payment requests, payments, receipts | 2 days |
| 12.7 | Visits, notices, freeze, Me, join | 2 days |
| 12.8 | Notifications | 1 day |
| 12.9 | Tests (unit, double-tap, Maestro flows), the `.apk` test build, an Expo Go guide for iPhone testers, PLAN and DEPLOY updated. iPhone testers sign Expo Go in to a shared testers' Expo account: on a real iPhone, Expo Go opens a project from the Mac only when both use the same account | 2 days |

**About 3 weeks.** Done when: a member can install the test `.apk`, sign in, show a QR the kiosk accepts with the phone offline, renew and see the gym's approval arrive without touching anything, get a notification on Android, and no tap anywhere sends two requests.

**Afterwards (not M12):** publishing to Google Play and the App Store (accounts, store listings and screenshots, privacy forms, app links), and the branded app per gym.

### 17.8 What the data model gains

| Table / column | Step |
|---|---|
| `push_subscriptions.kind`, `push_subscriptions.expo_token` (and `endpoint`, `p256dh`, `auth` nullable) | 12.2 |
| `idempotency_keys` keyed by member as well as staff | 12.2 |
| `member_sessions.client` (web, app) | 12.2 |

---

## 18. Next: what the pilot gyms asked for (M13–M15)

*Asked 2026-10-19.*

| Question | Answer |
|---|---|
| Door readers | Fingerprint and face readers on the door, which unlock it. Some gyms have **ZKTeco or eSSL** (eSSL readers are made by ZKTeco), some **Hikvision**: each gym chooses its brand (18.2) |
| Personal training | Some members ask for a trainer. Gyms charge **both** ways: a monthly fee, and packs of sessions |
| Trainers' pay | A **fixed salary**: an expense (18.1), with no commission to work out |
| Expenses | Some gyms want to track them |
| Supplements | Not asked for: they stay on the later list (§14) |

**Order.** M13, expenses, first: it is small and nothing blocks it. M14, the door readers, as soon as we know the pilot gyms' models and have a reader of each brand to test with: for a gym whose door opens by fingerprint or face, it is what stops an expired member walking in. M15, personal training, was to follow; it was built first (2026-10-19), with the first two small pilot helpers, while M14 waits on hardware. Notifications for staff followed (§18.6), then a demo gym (§18.7).

v1's rules apply to every step, as in §16: the gym from the token and a cross-gym 404 test for every new route, one specific permission per endpoint with a 403 test, money in paisa, every change in `activity_log`, every string in `en.json` and `ne.json`, a live event and a query-count test for each new list.

### 18.1 M13 — Expenses

What the gym spends — rent, salaries, bills — recorded at the desk, so Reports shows profit, not only income.

| | |
|---|---|
| Table | `expenses` (§6). Like payments, never deleted: a mistake is voided with a reason, and every edit goes to `activity_log` with before and after |
| Categories | Fixed, so they translate and add up the same way in every gym: rent · salaries · electricity · water · internet and phone · equipment · repairs · cleaning and supplies · marketing · taxes and fees · other. A trainer's salary is *salaries*, with their name in *paid to* |
| Permissions | **Record expenses** (`expenses.record`) and **Edit and void expenses** (`expenses.edit`), an *Expenses* area of their own; both in the *Manager* starting point, neither in *Front desk*. The list and its totals need **See money totals and reports**, as Payments does, because salaries are in it: someone who may only record sees the form, not the list |
| Branches | An expense is for one branch, or (null) the whole gym. Staff limited to some branches record for one of theirs and see only theirs; whole-gym expenses are for those who work at every branch |
| Date | `spent_on`, a Nepal day, today unless changed, never after today; entered in AD or BS like every date |
| Screen | **Money and numbers → Expenses**: a month of the gym's own calendar (BS months for a gym showing BS, as Reports), spent this month and by category, then every expense: date, category, paid to, method, branch, who recorded it. **Add expense**; on each one *Edit*, *Same again* (the form filled in from it, dated today: rent and salaries come every month) and *Void* with a reason. *Add an expense* is also in search (Ctrl/⌘K) |
| Reports | Monthly: **Spent**, **Profit** (income − spent), spent by category, each against the month before. The income chart becomes money in and out by month |
| Export | `expenses.xlsx` on Import / export, with the same permission as payments |
| API | `GET /expenses?month=&category=` (the month's expenses, the total and by category) · `POST /expenses`, with an `Idempotency-Key` (a double tap must not record the rent twice) · `PATCH /expenses/{id}` · `POST /expenses/{id}/void` |
| Live | An `expense` event, heard by staff who see money at that branch; the Expenses screen reloads |
| Later | A photo of the bill; expenses that repeat by themselves; a till total that takes off cash paid out |

### 18.2 M14 — Door readers: ZKTeco / eSSL and Hikvision

Pilot gyms have both brands. **The brand is chosen for each reader**: when the gym adds one in Settings → Door scanners, it picks *ZKTeco / eSSL* or *Hikvision* and the branch it is at, so a gym with two branches can have one of each. Behind the choice is one reader interface with an adapter per brand, the way SMS has one interface and an adapter per gateway (§3): the door rules, Attendance and the member's visits never know which brand it was.

Whatever the brand:

- Fingerprints and faces stay on the reader; GymBhai stores only which reader user is which member (§4.3). A member enrols at the reader itself, once.
- GymBhai adds a member to the reader when a membership starts or is renewed, and takes them off when it ends or is frozen. The reader then refuses an expired member by itself, and keeps working when the internet drops.
- Each scan the reader reports becomes a check-in through the same service as a QR scan (method `fingerprint` or `face`), under the same rules.

| | ZKTeco / eSSL | Hikvision |
|---|---|---|
| Talking to GymBhai | Models with **ADMS** (*Cloud server setting* in the Comm menu) send each scan to GymBhai over HTTP and collect commands from it: nothing else needed at the gym | Readers are managed through **ISAPI** on the gym's own network, which GymBhai can't reach from the internet: a small bridge at the gym (a PC or a Raspberry Pi) passes commands on. The reader can send its scans out to GymBhai by itself. Hikvision's **ISUP**, where the reader connects out to us, would avoid the bridge but is more work |
| Older models | Those that only speak the local-network protocol need the same bridge | — |
| An expired member | Taken off the reader when the membership ends | Each user on the reader can carry an end date, so it refuses them from that day even before GymBhai catches up |

The details of each protocol are confirmed on a real reader before a gym relies on it. First step: each pilot gym's brand and model (the label on the back, or Menu → System Info) and whether the reader is connected to the internet; then one reader of each brand to build and test with.

**Built before a reader, 2026-10-20**, to the makers' published protocols and tested against a simulated reader (`docs/READERS.md` has the set-up and the list to confirm):

| | |
|---|---|
| Adding one | Settings → Door scanners → *Add a fingerprint or face reader*: brand, name, branch, serial number (needed for ZKTeco). Then how to point it at GymBhai: for ZKTeco the reader's *Cloud Server Setting*; for Hikvision the bridge's settings, with the reader's token shown once. The list shows each reader's members on it and changes waiting |
| Who goes on it | Every member with a current, upcoming or recent membership, under their **reader number**: the digits of their member code, shown on their profile, to enrol them under. Taken off 90 days after they stopped coming, or when archived or erased. Each carries the last day it should let them in: none while expired, frozen, not started, or on a plan not sold at that branch |
| How it's kept up to date | Pulled, not pushed: the reader (or bridge) asks every few seconds, and GymBhai works out then what it should hold, at most every 30 seconds, and hands out the changes not yet answered (again after 2 minutes without an answer). Nothing to schedule; an offline reader catches up |
| Scans | Check-ins under the same rules as a QR scan, dated when the member was at the door (`fingerprint`, `face`, `card`, `pin`); sent twice, recorded once. Ignored: scans from before the reader was added, users who aren't members, and times in the future |
| ZKTeco / eSSL | ADMS at `/iclock/*` (HTTPS through Caddy; plain HTTP for old firmware is an opt-in Caddy site, docs/READERS.md). Members are put on with their number and name. **It doesn't yet refuse an expired member by itself**: GymBhai records the scan as denied, so the desk sees it. How a model refuses someone without losing their fingerprints is the first thing to confirm |
| Hikvision | The bridge (`bridge/hikvision_bridge.py`, Python with nothing to install) makes the changes over ISAPI with each member's end date, so **the reader refuses an expired or frozen member by itself**, and reads the reader's event log for scans. It signs in with the reader's device token, as a kiosk does; a reader's token can't use the kiosk's routes, nor a kiosk's the bridge's. The reader pushing scans out by itself (no bridge for scans) is left for when we have one to try |
| Not yet | Mapping a reader's existing users (enrolled before GymBhai, under other numbers) to members: until then GymBhai manages a reader's users from its own numbers, and ignores others; door control for ZKTeco; Hikvision's ISUP (no bridge); readers that only speak the local protocol |

### 18.3 M15 — Personal training

Built before M14, which waits on hardware. From the pilot gyms: PT is sold both as a monthly fee and as packs of sessions; trainers are on a salary (an expense, 18.1), so there is no commission to work out.

| | |
|---|---|
| PT plans | **Settings → Personal training**: the gym's own PT plans, like membership plans: a name, **Monthly** (training for the plan's length) or **Pack of sessions** (N sessions to use within the plan's length, e.g. 12 sessions in 2 months), the length in months or days, and the price. Hide one to stop selling it. *Plans and prices* permission to change them; staff who sell PT see them |
| Trainers | A trainer is a staff account with the new permission **Train members** (`pt.train`): they appear in the trainer list, see their own clients and record their sessions. A new *Trainer* starting point: Train members, View members, Check members in. The owner, who has every permission, is in the list too. The *Manager* starting point leaves Train members out: it makes someone a trainer, which is a job, not a level of trust. A disabled account leaves the list; its packages keep it until changed |
| Selling | Member profile → **Personal training** tab → **Sell personal training**: plan, trainer (the seller, if they train), start date (today), price and discount from the plan, payment taken now (full, part or nothing; needs *Collect payments*), with an `Idempotency-Key`. The end date comes from the plan's length in the gym's calendar, as for memberships. The branch is the member's home branch unless chosen (a gym with several): staff limited to some branches see the packages, and their payments, there. Not for an archived member. New permission **Sell personal training** (`pt.sell`): the sale, changing the trainer or dates, cancelling, and recording or voiding anyone's sessions; in the *Front desk* and *Manager* starting points |
| A package | What was sold, its own row, with the plan's name, kind, sessions and price copied, so changing the plan later changes nothing sold. Status is computed, never stored: upcoming, active, **used up** (a pack with every session recorded), ended, cancelled. Dues: price − discount − payments + refunds. **Change trainer or dates**, with a reason, but never leaving a recorded session outside the dates. **Cancel** with a reason and an optional refund (*Record refunds*) |
| Sessions | **Record a session** (a day, today unless changed, never in the future; a note staff see and the member doesn't): by its trainer, or anyone with *Sell personal training*. Within the package's dates, not on a cancelled package, never more than a pack holds (the package is locked while counting, so two at once can't both take the last). Each session keeps the trainer of that day. A mistake is voided with a reason, never deleted, which frees its place in a pack. A monthly package's sessions are the trainer's attendance record, with no limit. The note stays out of the activity log, and erasing the member clears it |
| Money | PT payments are ordinary payments (`payments.pt_package_id` instead of `membership_id`, never both), with a receipt number; they show in Payments (marked *Personal training*), Today, Reports and the exports (a *For* column) like any other, and void and edit the same way. The receipt names the PT plan and its dates. *Collect payments* takes money towards a package, from its card. A membership's dues never count PT payments, nor the other way round. A package's dues show on its card, on the trainers' lists, on the member's Home, and in Follow up (below) |
| Screens | **Personal training** in the Desk menu: **My clients** for a trainer (their upcoming and active packages: sessions left or so far, ends on, last session, Record session) and **All** for *Sell personal training*, by trainer, or one trainer. Used-up and ended packages leave the lists. The member's profile tab lists every package with its sessions, payments and actions; its History tab includes personal training. Search (Ctrl K) has *Record a training session* for trainers |
| The member | The app's Home shows their personal training still to come or under way: plan, trainer, sessions left or days left, anything owed on it (web and phone app) |
| Live | A `pt` event for the PT screens, heard by staff who train or sell at that branch; the member's own app and profile hear a `member` event |
| API | §8, *Personal training* |
| Reminders | Added 2026-10-20. Two automations in Messages → Automations, under *Personal training*, off to start like every automation but expiry. **Ends** (`pt_ending`): days before or after a member's personal training ends (−60 to 60), counted from their last package, so someone who has bought the next one isn't told; a pack used up early ends on the day of its last session, and gets the on-the-day and after messages from then (a *before* can't be timed for it). **Money still owed** (`pt_dues`): days after the sale (1 to 90), still owing on that package. `{plan}` is the PT plan, `{trainer}` the trainer's first name, `{amount}` what's left to pay, the rest as for memberships. Once per rule and package (`dedupe_key` `pt:<id>`), by push first like every automation; tapping opens the app's Home, where the training is. New gyms start with three: three days before it ends, the day after (which reaches a pack used up early, the morning after its last session) and a week after the sale; migration 0025 adds them, off and in the gym's language, to gyms already there |
| Follow up | **Owe money** has a second list, *Personal training*: each package with money owed, at the caller's branches (member, PT plan, trainer, owed), most owed first, with **Call**, **WhatsApp** (a new purpose, `pt_dues`: the automation's wording with what they owe on personal training) and **Send message**. The tab counts both lists. Today's *owe money* stays memberships' |
| Reports | A *Personal training* card, for a gym with PT plans: PT income in the month (already within income), packages sold, sessions trained, members training (a package during the month), and by trainer: their members and the sessions they trained. At the caller's branches, like the rest |
| Not yet | Commission (no gym asked); workout and diet plans; class booking |

### 18.4 Signing in at the desk with a QR

The first of the small pilot helpers (§18). A member signs in on their phone with no SMS code: the pilot doesn't wait for an SMS gateway, sign-in costs nothing, and "I've a new phone" is solved at the desk.

| | |
|---|---|
| At the desk | Member profile → More → **Sign in on their phone** (*Turn app access on/off*, now in the *Front desk* starting point). A QR, a countdown, and **Show a new QR** once it runs out. When their phone signs in, the profile hears it live and the dialog says *Signed in on their phone*. The profile's Overview shows when they last signed in to the app |
| The member | Scans it with the phone's camera: the browser opens the member app, which signs in and takes the token out of the address. Or, inside the installed app — on an iPhone the Home Screen app doesn't share Safari's sign-in — **Scan the QR at the desk** on the sign-in screen, with the back camera. The phone app has the same button, and its poster scan signs in too when it finds a desk QR |
| The QR | The gym's member address with `#desk=<token>`: random, HMAC-stored, once, 5 minutes, only the newest per member, only at its own gym, only while app access is on (§11). A family phone signed in as someone else is signed out of them first, notifications included |
| API | `POST /members/{id}/sign-in-link` → `{url, made_at, expires_at}` · `POST /m/{slug}/desk-sign-in` `{token, client}` → the same answer as a code (web: cookie; app: refresh token) |
| Table | `member_sign_in_links` (§6) |

### 18.5 WhatsApp buttons

The second pilot helper. Members in Nepal read WhatsApp; an SMS costs the gym a credit. So beside every **Call**, a **WhatsApp** that opens a chat with the member from the desk's own phone, the message already written. It goes when someone presses Send in WhatsApp: free, and nothing passes through us. No WhatsApp Business API, no account to set up (an API with templates and automatic sending stays on the later list, §14).

| | |
|---|---|
| Where | **Follow up**, every row, its wording by tab: ending soon and lapsed → the renewal reminder, owe money → money owed, not visiting → we've missed you. **Today**: ending today, and enquiries to call back. **Member profile** → More → **Send on WhatsApp**. **Enquiry** dialog, beside the number |
| The message | The gym's own wording, as its SMS would say it now, filled in for the member: the renewal reminder is the one Follow up's *Remind* sends (the nearest expiry rule), money owed and not visiting are the gym's automation wording (its default if it has none), and the welcome is the desk's welcome SMS with the app's link. The dialog lets the desk pick another and edit it before WhatsApp opens. From the profile it starts on the welcome for someone who has never signed in to the app, else the reminder. Enquiries aren't members yet: their button just opens the chat |
| Permission | *View members*, like calling: no SMS permission, as no SMS is sent |
| The link | `https://wa.me/977<number>?text=…`; WhatsApp opens on the phone or the computer |
| API | `GET /members/{id}/message?purpose=reminder\|dues\|not_visiting\|welcome\|pt_dues` → `{text, phone}`; sends nothing |
| Not recorded | We can't know whether it was sent, so it isn't in the SMS log; a call isn't either |

### 18.6 Notifications for staff

The third pilot helper, designed 2026-10-19. A member's "I've paid" waits until someone approves it, and the dashboard's red count only helps while a screen is open. A notification on the owner's or the desk's phone says so at once. Web Push, as members have it (§16.3, 8.3): our VAPID key and the browsers' own push services, so it costs nothing and needs no SMS.

| | |
|---|---|
| What | The three things a member does that someone at the gym must answer: **a payment sent from the app** (to approve), **a freeze request**, and **an enquiry from the join form**. Each goes to the staff who could act on it, at the branches their screens already show: *Approve app payments* for the whole gym, *Freeze* by the member's home branch, *Enquiries* by the enquiry's branch (one with no branch goes to staff who work at every branch). The owner, who has every permission, gets all three |
| Turning it on | **My account → Notifications**: *Turn on* for this phone or computer (the browser asks once), and a tick for each of the three the person may get, all ticked to start. Each device is turned on by itself. A card on Today offers it once to staff who would get any, until it's on or put away with *Not now* |
| The message | Short, in the staff member's own language (English or Nepali, kept beside the SMS defaults): *Payment to approve: Sita Rai, Rs 1,500 for 1 month*; *Freeze request: Sita Rai, 10 days from 5 Kartik*; *New enquiry: Ram Thapa, 98XXXXXXXX*. A newer one of the same kind replaces the last on the phone, and says how many are waiting: *3 payments to approve*. Tapping it opens the list: Payment requests, Freeze requests or Enquiries |
| Signed out, it stops | A device's notifications belong to the sign-in that turned them on. Signing out, being signed out from My account or by the owner from Staff, a disabled account, a removed permission, or the sign-in running out (30 days) stops them at once: a lost phone stops showing members' names and payments. Signing in again in the same browser, as the same person, picks them up again without asking; anyone else signing in there starts with them off |
| iPhone | An iPhone gives Web Push only to a web app added to the Home Screen (iOS 16.4+), so the dashboard gets its own manifest (*GymBhai*, opening `/staff`) and My account shows how to add it, as the member app does. Android phones and computers need nothing |
| How it's sent | From the worker, like members' push: a job for each staff member, retried while a push service fails for now; a subscription the push service says is gone is turned off. No SMS instead: the red counts and the lists are still there. The dashboard gets its own small service worker (`/staff-sw.js`, scope `/staff`) that shows notifications and nothing else: no copies of staff pages are kept offline |
| API | `GET /auth/push?endpoint=` (the key, on or off here, the ticks) · `POST /auth/push` (this device on) · `POST /auth/push/resume` (signed in again here) · `POST /auth/push/off` · `PUT /auth/me/notifications` (the ticks). Each is the caller's own, like `/auth/sessions` |
| Table | `staff_push_subscriptions`: `staff_user_id`, `session_id`, `endpoint`, `p256dh`, `auth`, `user_agent`, `last_ok_at`, `revoked_at`. `staff_users.muted_notifications`: the kinds someone turned off, so a kind added later starts on |
| Built | 2026-10-19: `app/services/push/staff.py` (who gets what, the worker's send), `app/core/staff_push_text.py` (the wording), `public/staff-sw.js`, `public/staff.webmanifest`, My account's Notifications card and Today's offer. Turning off tells the server and leaves the browser's own subscription alone: on a shared desk computer, a colleague may have turned the same browser on for themselves. Migration 0023 |
| Not yet | The owner's daily summary (§9, by SMS today) as a notification; quiet hours (the phone's own Do Not Disturb does that); notifications about the door, SMS credit or our subscription; a phone app for staff |

### 18.7 A demo gym

The last pilot helper, 2026-10-20: a gym that looks lived-in, for showing GymBhai to a gym and for trying a screen with real-looking numbers.

| | |
|---|---|
| Run | `make seed-demo` (`scripts/seed_demo.py`): removes the gym `/demo` if it is there and makes it again, in seconds. It refuses to run in production: everyone in it is made up, and its staff share one password, `demo-password-123` |
| The gym | *Himalayan Fitness Club*, two branches (Baneshwor, Koteshwor), plans counted and dates shown in BS. The four plans priced, an off-peak *Morning 1 month* and a *10 visits* pack; eSewa, Khalti and bank accounts; the join form on |
| Who | The owner (9800000200), a front desk (…201), and two trainers limited to a branch each (…202, …203), made from the starting points. 170 members with Nepali names, joined over the year, some referred by others; members sign in to the app with `MASTER_OTP` |
| A year of it | Memberships one after another, most renewed a few days early, some after a gap, some left to lapse; paid in full or in part, the rest later or still owed; freezes. About 8,500 visits: each member's own habit, mornings or evenings, quieter Saturdays, some who stopped coming, a few turned away. Rent, salaries and bills in each BS month, equipment twice. Enquiries open, joined and lost; personal training with its sessions; three notices; two app payments and a freeze request waiting |
| Dated | Made through the same services as the desk, each action dated when it happened (activity log, payments, created dates), so History, Reports and Today read like a year at a gym. The same people and habits every run; the dates follow today |
| Tested | `tests/integration/test_seed_demo.py` builds a small one in the test database: it still builds as the services change, no membership is paid beyond what it owed, every visit falls within its membership, and a second run makes the same gym |

### 18.8 What the data model gains

| Table / column | Step |
|---|---|
| `expenses` | M13 |
| `member_sign_in_links` | 18.4 |
| `pt_plans`, `pt_packages`, `pt_sessions`, `payments.pt_package_id` | M15 |
| `reminder_rules.trigger` gains `pt_ending`, `pt_dues` | M15 (reminders) |
| `staff_push_subscriptions`, `staff_users.muted_notifications` | 18.6 |
| `reader_users`; `devices.kind`, `serial`, `synced_at`, `command_seq` | M14 |

---

## 19. Next: from the later list (M16–M20)

*Planned 2026-10-20*, before the pilot: five items from the later list (§14). Family and couple plans, a kiosk that works offline, WhatsApp messages, classes, and progress tracking. The pilot gyms haven't asked for any of them yet (§18), so first ask them the questions below. Their answers may change the order or cut a step.

**Order.**
1. **M16, family and couple plans.** Gyms already make plans called "Couple — 1 year" (§5.1). They sell them as two memberships with the price split by hand, so the door can't tell that the second person owes anything. It touches money, so it goes before anything else builds on memberships.
2. **M17, the kiosk offline.** The kiosk is how most members get in, and a gym's internet drops. A door that stops is the worst day a gym can have with us. Fingerprint and face readers already work offline (§18.2).
3. **M18, WhatsApp messages.** About a week of code, but Meta's business verification and template approvals take days to weeks. **Start them on the first day of M16.**
4. **M19, classes.** The largest: the staff dashboard, the member web app and the phone app. Worth it for gyms that run Zumba, yoga or aerobics at fixed times.
5. **M20, progress tracking.** The least risk: it touches nobody's money or door. It gives members a reason to open the app between renewals.

| To ask the pilot gyms | For |
|---|---|
| Do you sell couple or family memberships? For how many people? Does one person pay? Does each newcomer pay the admission fee? | M16's shape |
| How often does the internet go down at the door, and for how long? | Whether M17 is second, and how long the kiosk must last offline |
| Do members ask for messages on WhatsApp rather than SMS? | M18 |
| Which classes do you run at fixed times? Are places limited? Are classes part of the membership, or paid separately? | M19's shape, or whether it waits |
| Do trainers weigh and measure members now: on paper, or with a machine such as an InBody? | M20 |

v1's rules apply to every step, as in §16 and §18: the gym from the token and a cross-gym 404 test for every new route, one specific permission per endpoint with a 403 test, money in paisa, every change in `activity_log`, every string in `en.json` and `ne.json`, a live event and a query-count test for each new list. Each member-facing step lands in the web app and the phone app (§17) together.

### 19.1 M16 — Family and couple plans

One sale covers two or more people (a couple, or a parent and children) at one price, paid by one of them.

**The idea: everyone has their own membership, and one of them carries the money.** Each person keeps an ordinary membership row: their own dates, status, freezes, QR, visits and door rules, exactly as now. The payer's membership carries the whole price, the discount, the admission fees and every payment; the others carry nothing. A `membership_groups` row ties them together. So the status code doesn't change, the dues code barely does, and Reports counts people as people and money once.

| | |
|---|---|
| Plans | A plan gains **People** (`plans.seats`, 1 to 6, 1 as now): *Couple — 1 year* is 2, *Family — 3 months* up to 4. Set in Settings → Plans and prices (*Plans and prices* permission); the price is for everyone together. A plan for several people can't be a visit pack: whose visits would they be? |
| Selling | Add member and Renew, with such a plan, ask **Who else?**: up to seats − 1 members, found by name, phone or code, or added there (name and phone, with the payer's phone offered for a child). Fewer than seats is fine: a family plan for 3 of 4. The member it's sold from pays, unless changed. One `Idempotency-Key` for the sale. Everyone's membership is made in one transaction, each member locked in id order so two desks can't deadlock. Not for an archived member |
| Dates | Everyone starts and ends on the sale's dates by default. A renewal starts each person the day after their own current membership ends (§5.3), so nobody loses days. Their dates can then differ, for example when a freeze moves one person's end date |
| Money | On the payer's membership: the price, the discount, and the plan's admission fee for each person on their first membership (the desk can change it). The others carry 0. The group's dues are the payer's membership's dues. **The door uses the group's dues**: the gym's dues rule (§5.3) applies to everyone in the group, not only the payer. The receipt names the payer and lists everyone covered |
| Changes | **Add someone** to a free place: from today (or a chosen day) to the payer's end date, price unchanged unless edited (*Sell and renew*). **Remove someone**: cancels their membership with a reason, price unchanged unless edited (*Cancel*). Any refund goes to the payer, as now. **Change plan** only to a plan for the same number of people. Freezes, extensions, *Extend everyone* and dates stay per person. Cancelling the payer's membership cancels the whole group, after one confirmation that lists everyone. Every change is in the activity log and on everyone's History |
| The member | Each person sees their own membership: *Couple — 1 year, with Ram Rai*. Only the payer sees the dues; the others see *Ram pays for this*. **Renew from the app**: the payer renews the group (the payment request carries the people, and approving it sells to all of them, §5.4). The others may buy a plan for themselves, or ask the payer |
| Reminders | Expiry and dues messages go to the payer only, naming the plan: one message per family, not one per person to the same phone. The others still get notices, birthday messages and not-visiting messages |
| Lists and reports | Members and Follow up's *ending soon* and *lapsed* list everyone, under the plan's name. *Owe money* lists the payer. On Reports, new members and renewals count people, and income counts the money once, since it's all on the payer's membership |
| Import | A register's couple rows import as single memberships, as now (imports carry no price anyway) |
| API | `seats` in the plan routes · `POST /members/{id}/memberships` takes `with_member_ids` · `GET /membership-groups/{id}` · `POST /membership-groups/{id}/members` (add someone) · removing someone is `POST /memberships/{id}/cancel`, as now |
| Built | 2026-10-20. `memberships.sell` makes the group and everyone's membership in one transaction, the members locked in id order; `group_dues_for` gives the door, the member's profile and the app what the payer still owes (no query without a family plan); the payer's cancel and plan change carry everyone, and the payer's membership is deleted last. The others on a sale hear by push only, free. Desk: *People* in the plan form, *Who else is on it?* in the sale form (find a member, or add someone new with a parent's number), *On this plan* on the membership with *Add someone* and *Remove from plan*. Migration 0026; `tests/integration/test_family_plans.py` |
| Not yet | Changing who pays; one person's share paid separately; groups of more than 6; groups for personal training |

### 19.2 M17 — The kiosk keeps working offline

Today the kiosk needs the internet (§4.3). When it drops, the kiosk says so and the desk checks people in by hand. From M17 the kiosk keeps letting the right people in for up to **3 days** offline (a gym setting, 1 to 7), and the visits reach GymBhai once it's back online.

| | |
|---|---|
| What it keeps | A **roster** for its branch, fetched when the kiosk opens and every 5 minutes while online (`GET /kiosk/roster`). It lists each member with a membership in the last 90 days, or one still to come. For each one: name, member code, a small photo, and the days they may come in the next 14 days, with freezes, a membership starting next week and the branch already applied. Also: grace days, an off-peak plan's hours, visits left on a pack, whether they owe money (and the gym's dues rule), and the re-scan window. No phone numbers, emails, notes or amounts: a stolen kiosk holds as little as possible |
| Where | In the kiosk browser's own storage. The kiosk becomes an installable app (`/kiosk.webmanifest`, full screen) with its own service worker (`/kiosk-sw.js`, scope `/kiosk`), which keeps the kiosk page, its build assets and members' photos, and nothing else. Revoking the device wipes the roster the next time the kiosk reaches GymBhai |
| Deciding offline | The roster's **letters**, one a day for 14 days, are the server's own rules for that day (`app/services/kiosk.py`, from the same member state as the door): *a* let in, *g* expired within the grace days, *f* frozen, *x* expired or not started, *b* another branch's plan, *v* every visit used. The kiosk adds the rest (`shared/src/door/offline.ts`): the hour, money owed and the dues rule, visits it let in since the roster came, and the re-scan window. `shared/src/door/cases.json` holds a member in each situation with the server's answer; the server's tests write and check it (`UPDATE_DOOR_CASES=1`), and the kiosk's tests check the kiosk gives the same answers. The kiosk uses the server's clock: it keeps its offset from the roster's `server_time` |
| Checking a QR | **Printed cards:** the roster holds a hash of each card token. **The app's QR:** today's code is an HMAC, and anything that can check an HMAC can also make one. A kiosk holding members' keys could forge a code for any of them, online too. So the app moves to a **new code, `gb2`, signed with Ed25519**. The phone holds a private key derived from the member's secret and `qr_version`, and the roster holds only the public keys, so a kiosk can check a code but never make one. The code is `gb2.<member>.<window>.<signature>`: about 120 characters, still a small QR. The server accepts both `gb1` and `gb2`; the apps switch to `gb2` the next time they open online. The phone signs with `@noble/ed25519`, plain TypeScript (no WebCrypto, so the QR still draws offline and over plain HTTP). The server uses `cryptography`, already installed with `pywebpush`. One shared test vector, as now. The web app updates itself; the phone app needs an update. Offline, an old app's `gb1` code shows *This code needs the internet. Please see the desk* |
| Recording | The kiosk keeps each offline scan with its own id and time, and with what it decided: that is what happened at the door. Once online, it sends them in batches to `POST /kiosk/scans`. The server records each one as a check-in with that result and time, and never decides it again. `check_ins.offline` marks them, and `client_id`, unique per device, means a scan sent twice is recorded once. Times are checked as a reader's are (§18.2): not before the roster was fetched, and not in the future |
| Visit packs | Counted on the kiosk. Two offline kiosks at one branch could both let someone in on their last visit. That rare extra visit is recorded, and not worth a lock |
| On screen | Offline with a roster, an amber band: *No internet — letting members in from the list saved at 10:42*, and how many visits are waiting to be sent; the same green, orange and red cards (money owed shows orange, without the amount). Past the limit, or with no roster: red, and the desk checks people in by hand. On Today, for every staff member: a kiosk not heard from for 15 minutes to 12 hours (`devices.last_seen_at`). Once it syncs, its visits appear in Attendance at their real times. A scan the server hasn't answered in 4 seconds is decided offline |
| Built | 2026-10-20. Settings → Check-in rules: *Kiosk works offline for (days)*, 1 to 7. Scans waiting are sent before a new roster is fetched, so the roster's visit counts include them. `gb2` in `app/core/qr.py` and `shared/src/qr/memberQr.ts` (Ed25519 passed in from each app's `lib/ed25519.ts`: `shared/` has no packages), with one test vector on both sides. Migration 0027; `tests/integration/test_offline_kiosk.py`, `frontend/src/lib/doorOffline.test.ts` and `kioskOffline.test.ts`; the phone app bundled for Android with Ed25519 |
| Not yet | The staff phone's Scan and manual check-in offline (they run in the dashboard, which needs the internet); the money owed on the card offline |

### 19.3 M18 — WhatsApp messages

GymBhai sends reminders and answers by WhatsApp, between push (free) and SMS. Most members read WhatsApp. A Nepali reminder is often 2 or 3 SMS (70 characters each, §10) but always one WhatsApp message. This is separate from §18.5's buttons, which open a chat on the desk's own phone; they stay as they are.

| | |
|---|---|
| How | Meta's **WhatsApp Cloud API**, directly, with no reseller. It sits behind a provider interface, as SMS does: `console` in development and tests, `meta` for real (`WHATSAPP_PROVIDER`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`) |
| Whose number | **One GymBhai number for every gym**, to start: one Meta business to verify (ours), not one per gym. Every message starts with the gym's name. A gym's own number (Meta's Embedded Signup, with us as a Tech Provider) is a later add-on |
| Which messages | Only Meta's **utility** category, at about **$0.011 (about Rs 1.5) a message** (Rest of Asia Pacific rates, read 2026-10-20 from summaries of Meta's rate card; confirm Nepal's market on the card itself). That covers: membership ending (the expiry automations), money still owed (memberships and PT), payment approved or rejected, freeze request answered, the receipt with its link, and the welcome with the app's link. **Marketing** messages (win-back, birthday, not visiting, notices) cost about $0.084, more than an SMS, so they stay push first, then SMS |
| The wording | WhatsApp sends only **templates Meta has approved**, so the gym's own SMS wording can't be used. Each message is one of our templates, in English and in Nepali, with the gym's details filled in (`{name}`, `{gym}`, `{date}`, `{amount}`, `{link}`). Messages → Automations shows each rule's WhatsApp wording beside its SMS. The templates live in `app/core/whatsapp_templates.py`; a test checks that each has both languages and the variables Meta approved |
| The order | `notify` (§16.3) becomes push → WhatsApp → SMS. Push wherever a phone takes it. Otherwise WhatsApp, if the gym turned it on and the member agreed. Otherwise SMS. If WhatsApp answers that the number isn't on WhatsApp, the SMS goes instead, and WhatsApp isn't tried for that member again for 30 days |
| Agreeing | Meta requires members to agree first. **Settings → Gym → Send messages by WhatsApp** (*Gym settings* permission), off to start. A tick on Add member and Edit, *Agrees to messages on WhatsApp*, and the member's own switch in the app (Profile on the web, Me on the phone). Off for imported members until they're asked |
| Replies | Members will reply to our number. GymBhai answers at most once a day per member, inside Meta's 24-hour window: *This number only sends messages from Himalayan Fitness Club. To reach them: <a wa.me link to the gym's phone>*. Meta has charged for these replies since October 2026; we pay for them. Replying *STOP* turns WhatsApp off for that member. There is no inbox in GymBhai |
| Credits | Gyms keep one balance, **message credits**, which is today's SMS credits under a new name. A WhatsApp message costs the number of credits set in `/admin` (`platform_settings`; pricing lives in the database, never in code). Charged when sent, given back if Meta reports it failed |
| The log | `sms_messages` gains `channel` (sms, whatsapp), `template`, `delivered_at` and `read_at`. The SMS log, the member's Messages tab and the credit ledger show both channels, with *Delivered* and *Read* from Meta's webhook (`GET` and `POST /whatsapp/webhook`, checked against the app secret's signature) |
| Before it can send | Outside the code: Meta Business verification for GymBhai (company documents), a phone number not already on WhatsApp, the display name approved, each template approved (about a day each), and a payment method on Meta. **Start these with M16** |
| Not yet | Sign-in codes by WhatsApp (Meta's authentication category costs about what an SMS does); a gym's own number; an inbox for replies; notices by WhatsApp |

### 19.4 M19 — Classes

Group classes at fixed times (Zumba, yoga, aerobics, CrossFit), booked from the app, with places counted.

| | |
|---|---|
| Classes | **Settings → Classes** (*Manage classes*): the gym's class types (name, length, places, a colour) and a **weekly timetable** for each branch: type, day, time, instructor (a staff account with *Teach classes*, or the owner), places. The worker makes each class from the timetable 4 weeks ahead (a daily task at 01:00, §9, and at once when the timetable changes). One class can then be moved, given another instructor or cancelled without touching the timetable. Changing the timetable changes only the classes nobody has booked yet |
| Who may book | A plan gains **Classes**: none, all, or chosen types (`plans.class_access`, copied onto the membership at sale like hours and visits). A class-only plan such as *Zumba — 1 month* is an ordinary plan with only Zumba ticked; the door treats it like any other. A member may book while a membership that allows that class covers its day, at its branch |
| Booking | From the app (web and phone) or at the desk. Booking opens 7 days ahead and closes 30 minutes before the start (gym settings). One booking per class per member. The class is locked while places are counted, so two people can't both take the last one. The phone app sends an `Idempotency-Key` (§17.4). When a class is **full**, members join the **waitlist**. A freed place goes to the first in line, who gets a push; this stops 2 hours before the start |
| Cancelling | A member can cancel up to 2 hours before the start (a setting); after that it counts as a late cancel. When the gym cancels a class, everyone booked is told: by push, and by SMS too if the gym ticks it |
| Attendance | The instructor's **roster**, on their phone: who's booked. Members who checked in at the door in the hour before the class are already ticked *came*; the instructor ticks the rest. Anyone not ticked by the end is a *no-show*. A booking is never a visit by itself: the door's check-in is what counts against a pack |
| No-shows | Off to start: N no-shows in 30 days means no booking for 7 days. Members see their own count |
| Staff screens | **Desk → Classes**: today and the week by branch, with time, class, instructor, booked against places, and the waitlist. Open a class for its roster, *Book a member* and *Cancel class*. Instructors see **My classes**. The member profile gains a *Classes* tab: bookings, attended, no-shows. Reports gain classes held, places filled and no-shows, by type and by instructor |
| The member | **Classes** in the app, opened from a *Book a class* card on Home (no new tab): this week or next, by day, with places left, updated live (`class` events reach the branch's members); Book, Join the waitlist, Cancel. Their branch's classes, and any they were booked into at another. A push an hour before (free, never SMS). Web and phone app |
| Permissions | A new *Classes* area. **Teach classes** (`classes.teach`): their own rosters and attendance; in the *Trainer* starting point. **Book classes for members** (`classes.book`): in *Front desk*. **Manage classes** (`classes.manage`): the timetable, and moving or cancelling a class; in *Manager* |
| Live | A `class` event: places left in the app, rosters at the desk |
| Built | 2026-10-20. `app/services/classes.py` (the timetable, booking, the waitlist, who came, the month), `app/api/routes/classes.py`; Desk → **Classes** (the week by day; a class's roster with *Book a member*, ticks for who came, *Change this class*, *Cancel class*; *My classes* for instructors); the member profile's **Classes** tab; *Classes it includes* in the plan form (a plan change brings the new plan's classes); a **Classes** card on Reports; booking rules in Settings → Classes (`PATCH /gym/class-rules`). Migration 0028; `tests/integration/test_classes.py`, with the cross-gym, permission and query-count tests |
| Not yet | Paying per class (a day pass or visit pack already covers a drop-in); rooms and equipment; a timetable poster or TV screen; repeating bookings ("every Monday"); telling members booked when a class is moved; classes for a branch's members only |

### 19.5 M20 — Progress tracking

Weight, measurements and photos over time: members see themselves change, and trainers can show them.

| | |
|---|---|
| A check | `progress_entries`: a day (today unless changed, never in the future), **weight** in kg to 0.1, **body fat** % (optional), and measurements in cm: chest, waist, hips, arm, thigh, each optional. Plus a note. Stored as whole numbers (grams, tenths of a percent, millimetres), as money is stored in paisa. Height is entered once on the member (`members.height_mm`), and BMI is computed from it, never stored |
| Who records | The member, in the app. Staff with the new **See and record progress** (`progress.record`, in the *Trainer* starting point), for members at their branches |
| Photos | Front, side and back, taken in the app. **Private**: only the member sees them, unless they tick *Let my trainer see*, which shares them with the trainers of their personal training (§18.3) and nobody else. Not even the owner can open them. On upload they are shrunk to 1,600 px and stripped of their location data (EXIF; adds Pillow). Short-lived signed links; never in exports or the activity log |
| Charts | In the member app: weight and each measurement over time (the shared chart kit), the change since the first check and since the last, and two photos side by side by date. Member profile → **Progress** tab: the same figures, and the photos only if shared |
| Changes | Whoever recorded an entry, or the member, can edit or delete it. The activity log records what was done but not the figures: a body's measurements are the member's own, like a PT session's note (§18.3) |
| Erasing | Erasing a member deletes their entries, photos and stored files (§11) |
| Reminder | An automation in Messages → Automations, under *Progress*, off to start: *Time for a progress check*, `days` (7 to 180, 30 to start) after their last check. **By push only**, so it's free: only members whose phone takes push are reminded, never by SMS instead. Once per check (`dedupe_key` `progress:<member>:<date of the check>`); tapping it opens Progress. Migration 0030 gives every gym the rule, off, in its language |
| Built | 2026-10-20. `app/services/progress.py`, `app/api/routes/progress.py`; the profile's **Progress** tab (*See and record progress*); the member's **Progress** from a Home card, on the web and the phone app, with the weight chart, every check, height, and photos to add, share, compare (web) and delete. The chart kit's line can fit its scale to the values (`fit`, `shared/src/niceRange.ts`; no wash under a line that doesn't start at zero); the phone app draws the same line (`mobile/src/components/WeightChart.tsx`). Photos shrunk to 1,600 px and stripped of EXIF with Pillow, served by 15-minute links. Erasing a member deletes it all. A check's day is chosen on the web and, by stepping as for a freeze, on the phone app. Migrations 0029 and 0030; `tests/integration/test_progress.py` |
| Not yet | Goals; importing a report from a body composition machine (InBody); workout and diet plans |

### 19.6 What the data model gains

| Table / column | Step |
|---|---|
| `plans.seats`; `membership_groups` (`gym_id`, `plan_id`, `payer_member_id`, `seats`, `created_by`); `memberships.group_id`; `payment_requests.with_member_ids` | M16 |
| `check_ins.offline`, `check_ins.client_id` (unique per device, where set); the gym setting `kiosk_offline_days` | M17 |
| `sms_messages.channel`, `template`, `delivered_at`, `read_at`; `members.whatsapp_agreed_at`, `whatsapp_unreachable_at`; the gym setting `whatsapp`; `platform_settings` (credits per WhatsApp message) | M18 |
| `class_types`; `class_slots` (the timetable); `classes` (`gym_id`, `branch_id`, `type_id`, `slot_id`, `starts_at`, `ends_at`, `instructor_id`, `places`, `cancelled_at`, `cancel_reason`); `class_bookings` (`gym_id`, `class_id`, `member_id`, `status`: booked, waitlist or cancelled; `late`, `attended`, `booked_at`, `cancelled_at`, `source`, `booked_by`); `plans.classes` and `class_type_ids`, copied to `memberships`; gym settings `class_booking_days`, `class_closes_minutes`, `class_cancel_hours`, `no_show_limit`, `no_show_block_days` | M19 |
| `progress_entries`; `progress_photos` (`gym_id`, `member_id`, `taken_on`, `pose`, `photo_key`, `shared`); `members.height_mm`; `reminder_rules.trigger` gains `progress` | M20 |
