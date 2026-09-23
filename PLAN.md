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

There are no fixed roles. The owner creates each staff account — name, phone or email, password — then ticks exactly what that person may do and in which branches. To save time the form offers **starting points** the owner can then change: *Manager* (almost everything), *Front desk* (members, renewals, payments, check-in), *Blank*.

| Area | Permission |
|---|---|
| Members | View members · Add members · Edit member details · Archive members · Turn app access on/off |
| Memberships | Sell and renew · Edit dates, price, discount and plan · Extend days · **Extend everyone** · Freeze · Cancel · Delete |
| Money | Collect payments · **Approve app payments** · Edit payments · Void payments · Record refunds · See money totals and reports |
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
- Same member scanned again within 3 hours (configurable) → "Already checked in", no duplicate visit.
- Dues outstanding → follows the gym's **dues rule** (§5.3): allow, allow with a warning, or refuse.
- Every scan, allowed or denied, is recorded — denied scans are how owners see who is trying to train unpaid.

**Kiosk registration:** the owner, or staff with the **Devices** permission, opens `/kiosk` on the device while signed in and chooses **"Use this device as the door scanner for <branch>"**. The device receives a long-lived device token (stored on it, revocable from Settings → Devices). The kiosk can only check people in — it cannot open the dashboard.

**Fingerprint and face devices (later).** Many gyms will want a fingerprint or face reader at the door, often wired to a turnstile or door lock. The check-in service is built so a device is just another source of check-ins:
- Readers from common brands (such as ZKTeco) keep the fingerprints and faces **on the device itself**; we store only which device user is which member. No biometric data reaches our server — simpler, and far safer for members' privacy.
- The device reports each scan to us, and we record it with the same rules as a QR scan.
- For a door that locks, we push the list of members allowed in to the device, so an expired membership is refused at the door even if the internet is down.
- Which devices to support is decided later (§15); nothing in v1 needs to change for it.

**Offline:** v1 needs internet at the kiosk. If it drops, the kiosk says so and the desk checks people in manually. An offline queue is on the later list.

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

Controls on the member's profile:

| Control | Effect |
|---|---|
| **App access** on / off | Off blocks sign-in and signs out their devices (e.g. a banned member) |
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
| `gyms` | `slug` (unique), `name`, `logo_key`, `brand_color`, `phone`, `address`, `sms_sender_name`, `settings` (JSON: plan month counting AD/BS, date display AD/BS/both, dues rule (allow / warn / refuse), grace days, re-scan window, reminder language), `status` |
| `branches` | `gym_id`, `name`, `address`, `phone`, `is_active` |
| `staff_users` | `gym_id` (null for platform admin), `name`, `email`, `phone`, `password_hash` — `email` and `phone` unique across all staff, so signing in never needs a gym name — `is_owner` (at most one per gym), `is_platform_admin`, `permissions` (list of permission keys, §2.1), `is_active`, `last_login_at` |
| `staff_branch_access` | `staff_user_id`, `branch_id` — empty means all branches |
| `members` | `gym_id`, `home_branch_id`, `member_code` (e.g. `FZ-0042`, unique per gym; the prefix is a gym setting, derived from the gym's initials at sign-up), `name`, `phone` (**not** unique — family members often share one number), `email`, `gender`, `date_of_birth`, `address`, `emergency_contact`, `photo_key` (a storage key, served by signed link), `joined_on`, `notes`, `app_access` (bool), `qr_secret`, `qr_version`, `card_token`, `is_archived` |

**Money and memberships**

| Table | Key columns |
|---|---|
| `plans` | `gym_id`, `name`, `duration_months` *or* `duration_days`, `price` (null until the owner sets it; such a plan can't be sold without a price entered at the desk), `admission_fee`, `all_branches`, `is_active`, `sort_order` — four seeded on sign-up (§5.1) |
| `plan_branches` | `plan_id`, `branch_id` — the branches a plan covers when `all_branches` is false |
| `memberships` | `gym_id`, `member_id`, `plan_id`, `plan_name` (copied at sale, like the price), `branch_id`, `start_date`, `end_date`, `price`, `discount`, `admission_fee`, `cancelled_at`, `cancel_reason`, `created_by`, `source` (desk, app_request, import) |
| `membership_freezes` | `gym_id`, `membership_id`, `from_date`, `to_date` (inclusive), `reason` — extends `end_date` by the frozen days; ending a freeze early gives the unused days back |
| `payments` | `gym_id`, `member_id`, `membership_id`, `kind` (payment, refund), `amount`, `method` (cash, esewa, khalti, fonepay, bank), `transaction_ref` (unique per gym when set), `paid_at`, `receipt_no` (sequential per gym), `received_by`, `note`, `voided_at`, `voided_by`, `void_reason` — a payment can't exceed what is owed on its membership, nor a refund what was paid |
| `gym_payment_methods` | `gym_id`, `kind` (esewa, khalti, fonepay, bank, other), `label`, `account_name`, `account_number`, `qr_image_key`, `is_active`, `sort_order` — the gym's own accounts, shown to members |
| `payment_requests` | `gym_id`, `member_id`, `plan_id`, `payment_method_id`, `amount`, `transaction_ref`, `screenshot_key`, `status` (pending, approved, rejected, withdrawn), `reviewed_by`, `reviewed_at`, `reject_reason`, `membership_id`, `payment_id` — a member's "I've paid" from the app (§5.4) |
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
| `check_ins` | `gym_id`, `branch_id`, `member_id`, `membership_id`, `at`, `method` (app_qr, card_qr, manual; later fingerprint, face), `result` (allowed, warned, override, duplicate, denied_expired, denied_frozen, denied_branch, denied_dues), `device_id`, `staff_user_id`, `note` (the reason for an override) |
| `devices` | `gym_id`, `branch_id`, `name`, `token_hash`, `last_seen_at`, `revoked_at` |
| `notices` | `gym_id`, `branch_id` (null = all), `title`, `body`, `published_at`, `send_sms` |
| `reminder_rules` | `gym_id`, `days_from_expiry` (−7, −3, 0, +3…), `template`, `enabled` |
| `reminder_log` | `gym_id`, `rule_id`, `membership_id`, `sms_message_id` — unique per rule and membership, so a reminder is never sent twice |
| `scheduled_runs` | `name`, `run_on` — unique pair; how several workers agree a daily task runs once a day |
| `sms_messages` | `gym_id`, `member_id`, `to`, `body`, `kind` (otp, welcome, reminder, notice, receipt), `status`, `provider_ref`, `segments`, `error`, `sent_at` |
| `jobs` | `kind`, `payload`, `run_at`, `attempts`, `locked_at`, `done_at`, `error` |

**Sign-in and audit**

| Table | Key columns |
|---|---|
| `otp_codes` | `gym_id`, `channel` (sms, email), `destination`, `code_hash`, `expires_at`, `attempts`, `consumed_at`, `ip` — a row is written even for an unknown number, so the rate limits also count guessing |
| `staff_sessions` | `staff_user_id`, `refresh_token_hash`, `previous_token_hash`, `rotated_at`, `user_agent`, `ip`, `expires_at`, `last_used_at`, `revoked_at` — one row per signed-in staff device; the refresh token rotates on every use (§11) |
| `member_sessions` | `member_id`, `refresh_token_hash`, `previous_token_hash`, `rotated_at`, `device_label`, `expires_at`, `last_used_at`, `revoked_at` |
| `activity_log` | `gym_id`, `actor_type`, `actor_id`, `action`, `entity`, `entity_id`, `changes` (JSON, before → after), `reason`, `ip`, `at` — powers the History tab (§5.6) |

**Our billing (gyms paying us)**

| Table | Key columns |
|---|---|
| `platform_plans` | `name`, `max_active_members`, `max_branches`, `monthly_price`, `included_sms`, `is_active` — **all prices live here and are edited from `/admin`; none are written into the code**, so pricing can be set and changed any time |
| `gym_subscriptions` | `gym_id`, `platform_plan_id`, `starts_on`, `ends_on`, `status` |
| `subscription_payments` | `gym_id`, `kind` (subscription, sms), `platform_plan_id`, `months`, `sms_credits`, `amount`, `transaction_ref`, `screenshot_key`, `status` (pending, approved, rejected), `submitted_by`, `reviewed_by`, `reviewed_at`, `reject_reason` — an owner's "we've paid you", for a plan or for SMS credits (§5.7) |
| `member_imports` | `gym_id`, `filename`, `status` (preview, committed), `headers`, `rows`, `mapping`, `result`, `created_by`, `committed_at` — an uploaded register, checked before anything is saved |
| `sms_credit_ledger` | `gym_id`, `change`, `reason`, `balance_after`, `sms_message_id` — top-ups and each SMS sent. The balance is the sum of `change` (rows written in one transaction share a timestamp, so "the latest row" is not reliable); changes lock the gym row so two sends can't spend one credit |

---

## 7. Screens

### How they look

One design system, defined as tokens in `frontend/src/app/globals.css` — brand ramp, canvas and surface colours, the `hairline` border, the card shadows — and built into the shared components (`Button`, `Card`/`ListCard`/`Stat`/`EmptyState`, `Field`, `Choice`, `StatusBadge`, `Dialog`, the inputs). Screens compose those; they don't invent their own colours or borders, so the whole product restyles from one file. Type is Inter, self-hosted by `next/font`.

Staff screens are light and dense — read all day in a bright room, with white cards on a cool canvas. The member app is deliberately bolder: a full-bleed header in the gym's own brand colour, the QR as the largest thing on the screen, big touch targets, an icon tab bar. The kiosk is dark and legible across a room. `/admin` keeps the dark bar so our console is never mistaken for a gym's dashboard.

### Staff dashboard (`/staff`)

| Screen | What's on it |
|---|---|
| **Today** | Check-ins today, checked in within the last 2 hours (roughly who's inside — there's no check-out), expiring this week, expired but still visiting, dues outstanding, money collected today |
| **Members** | Search by name, phone or code; filter by status, branch, plan, dues. **Add member** |
| **Member profile** | Photo, details, current membership with days left, history, payments, visits calendar, SMS sent. Buttons: **Renew**, **Collect payment**, **Freeze**, **Print card**, **Reissue card**, **Check in** |
| **Add member / Renew** | One screen: member details → plan → discount → payment taken now (full or part) → save. Sends the welcome or renewal SMS and prints or shares the receipt |
| **Expiring** | Due in 7 days, due today, lapsed in last 30 days, with **Send reminder now** and **Call** buttons |
| **Payment requests** | Members' app payments waiting for approval: amount, transaction ID, screenshot. **Approve** / **Reject** (§5.4). Red count in the menu |
| **Payments** | All payments, filter by date, method, staff; daily cash total for closing the till; edit or void (§5.6) |
| **Membership edit** | Every field in §5.6, plus **Extend everyone**, and a **History** tab showing each change, who made it, before and after |
| **Attendance** | Check-ins by day and hour, denied scans, busiest hours |
| **Reports** | Monthly: income by method, new members, renewals, lapsed, active count, renewal rate |
| **Notices** | Write a notice, choose branches, optionally send by SMS (shows SMS cost first) |
| **Staff** | Staff accounts: add, disable, reset password; permission checklist and branch access per person, with *Manager* / *Front desk* / *Blank* starting points |
| **Subscription** | Their plan with us, days left, pay and submit transaction ID, SMS credit balance and top-up |
| **Settings** | Gym profile, logo and colour, calendar (plan counting and date display), branches, plans, payment methods and QR images, reminder rules and wording, check-in rules, QR poster, devices, SMS credits |
| **Import / Export** | Upload an Excel/CSV register, map columns, preview, import members with their current expiry dates. Download members, memberships, payments and check-ins as Excel. Dates in a register may be AD or BS (a year of 2050 or more is read as BS). Imported memberships carry no price — what members paid before GymBhai isn't income in GymBhai — and no SMS is sent until the gym chooses "Resend welcome" |

### Member app (`/<gym-slug>`)

| Screen | What's on it |
|---|---|
| **Sign in** | Phone number (or email) → 6-digit code. If several members share that phone — a parent and their children — pick who you are |
| **Home** | Days left (large ring), expiry date in the gym's calendar setting, **their QR code**, visit streak, latest notice |
| **Renew** | Plans with prices → the gym's payment QR and account details → enter transaction ID or upload screenshot → *waiting for confirmation* → active, or the reason it was rejected |
| **Payments** | Every payment and receipt, dues if any, pending requests |
| **Visits** | Calendar of visits, count this month |
| **Notices** | From their gym |
| **Profile** | Their details (read-only in v1), sign out |

### Kiosk (`/kiosk`)

Full screen camera, large result card for 3 seconds, then back to scanning. Gym logo and clock when idle.

### Platform admin (`/admin`)

Gyms list with plan, active members, SMS balance, subscription end. Activate or extend a subscription after payment, top up SMS credits, suspend, reset an owner's password.

---

## 8. API outline

All under `/api/v1`. Staff routes take the gym from the token.

```
Auth
  POST /auth/register-gym            gym + owner + first branch + calendar choice, starts a trial
  POST /auth/login                   staff
  POST /auth/refresh | /auth/logout
  POST /m/{slug}/otp/request         member: send code by SMS or email; unknown → 404 wording in §5.5
  POST /m/{slug}/otp/verify          member: returns session + QR secret, or the list of
                                     members on that phone to choose from

Setup
  GET|PATCH  /gym
  CRUD       /branches  /staff  /plans  /reminder-rules  /devices
  POST       /gym/logo

Members
  GET|POST   /members                 search, filter, paginate
  GET|PATCH  /members/{id}
  POST       /members/{id}/photo
  POST       /members/{id}/card/reissue
  POST       /members/import          upload → preview
  POST       /members/import/{id}/commit
  GET        /export/{members|memberships|payments|check-ins}.xlsx

Our subscription
  GET   /subscription                plan, days left, SMS balance
  POST  /subscription/payment        transaction ID for us to verify

Memberships & money
  POST  /members/{id}/memberships     new or renewal (+ optional payment)
  POST  /memberships/{id}/freeze
  POST  /memberships/{id}/cancel
  PATCH /memberships/{id}             edit dates, price, discount, plan, branch (§5.6)
  POST  /memberships/{id}/extend      N days + reason
  POST  /memberships/extend-all       whole gym or one branch, N days + reason
  DELETE /memberships/{id}            only while it has no check-ins
  GET   /memberships/{id}/history
  POST  /payments                     collect, incl. part payment of dues and refunds
  PATCH /payments/{id}
  POST  /payments/{id}/void           owner only by default
  CRUD  /payment-methods             the gym's own QR images and accounts
  GET   /payment-requests?status=pending
  POST  /payment-requests/{id}/approve
  POST  /payment-requests/{id}/reject
  GET   /payments/{id}/receipt        printable / shareable

Check-in
  POST  /check-ins/scan               from kiosk (device token) or staff
  POST  /check-ins/manual
  GET   /check-ins

Lists & reports
  GET   /dashboard/today
  GET   /lists/expiring
  GET   /reports/monthly?month=2083-06

Messages
  CRUD  /notices
  POST  /members/{id}/sms             one-off reminder
  GET   /sms                          log + credit balance

Member app
  GET   /m/me   /m/me/payments   /m/me/visits   /m/notices
  GET   /m/plans   /m/payment-methods
  POST  /m/payment-requests          plan, method, transaction ID, screenshot

Member access (staff)
  PATCH /members/{id}/access          app access on/off
  POST  /members/{id}/resend-welcome
  POST  /members/{id}/sign-out-all

Platform admin
  GET   /admin/gyms
  GET   /admin/subscription-payments?status=pending
  POST  /admin/gyms/{id}/subscription
  POST  /admin/gyms/{id}/sms-credits
  POST  /admin/gyms/{id}/suspend
```

---

## 9. Background work (worker)

| Job | When | What |
|---|---|---|
| Renewal reminders | Daily 09:00 Nepal time | For each enabled rule, find members whose **chain of memberships** ends that many days away (or past) — so anyone who has already renewed is never reminded — and queue one SMS each, never the same rule twice for the same membership. A missed day is caught up for up to 2 days |
| Send SMS | Continuously | Take queued SMS, check the gym's credit, send, record result, retry failures 3 times with backoff |
| OTP | Immediately on request | Sent directly, not queued behind reminders |
| Daily summary *(optional)* | 20:00 | SMS to owner: "Today: 42 visits, Rs 18,500 collected, 6 expiring this week" — a feature owners notice |
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

- Staff passwords with bcrypt; short-lived access token (15 minutes, kept only in the page's memory), refresh token in an httpOnly `SameSite=Strict` cookie scoped to `/api/v1/auth`. The refresh token rotates on every use; the token it replaced still works for 30 seconds so two tabs refreshing together don't sign each other out, and never after. Only token hashes are stored.
- The browser only talks to the Next.js server, which forwards `/api/*` to FastAPI. Everything is same-origin: the cookie is first-party and there is no CORS.
- Every request re-reads the staff account, its session, permissions and branches from the database, which is what makes "takes effect immediately" (§2.1) true.
- API errors carry a stable `code` next to the English `detail`; the frontend translates by code, so Nepali never means parsing English.
- OTP: 6 digits, valid 5 minutes, 5 attempts, max 3 requests per phone per 15 minutes and a per-IP limit — each OTP costs us an SMS (they're never charged to the gym's credits, §5.7).
- A sign-in code is never left readable: the SMS log keeps "Sign-in code (hidden)", since staff with the SMS permission can read the log. For end-to-end tests `OTP_TEST_CODE` fixes the code; the app refuses to start with it outside local and test environments.
- Member tokens are a separate type from staff tokens; neither is accepted in place of the other. Kiosks authenticate with a device token (`X-Device-Token`), stored hashed, and can only reach `/kiosk/*`.
- Turning app access off, changing a member's phone or email, "Sign out all devices" and "Reissue QR" all revoke the member's sessions at once.
- Members only ever see their own records; checked in every `/m/` route.
- Tenant isolation test (§3) plus a permission test for every permission in §2.1: without it the action returns 403, and a staff member cannot grant a permission they don't hold.
- Every money action, check-in override, staff change and settings change goes to `activity_log`.
- Member photos served through signed, expiring URLs, not public links.
- Daily `pg_dump` to storage outside the server, kept 30 days; restore tested once before the first real gym goes live.

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

**Progress**

| # | Status |
|---|---|
| M0 | Done 2026-09-19 |
| M1 | Done 2026-09-19 |
| M2 | Done 2026-09-19 |
| M3 | Done 2026-09-19 |
| M4 | Done 2026-09-20 |
| M5 | Ready to deploy 2026-09-20: production stack (Caddy, R2 storage, nightly backups with restore, Sentry) verified locally; runbook in `docs/DEPLOY.md`, onboarding checklist in `docs/PILOT.md`. Waiting on: the server, the domain's DNS, the R2 buckets, an SMS gateway account (its adapter then tested live), and the pilot gyms |

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
- One VPS running Docker Compose (`docker-compose.prod.yml`), Caddy in front for HTTPS; Caddy sends `/api` straight to the API and everything else to the web app. Postgres on the same machine at first, with the off-site backups above (a `backup` container, 02:00 Nepal time, 30 days kept); move to managed Postgres when there are enough gyms to justify it. See `docs/DEPLOY.md`.
- Domain, SMS gateway account with credit, S3-compatible storage for photos and backups.
- Error tracking (Sentry free tier) and an uptime check.

---

## 14. After v1

Rough order, driven by what pilot gyms ask for and will pay for:

1. Automatic payment verification — Fonepay / eSewa merchant APIs confirm an app payment so it activates without staff approval; needs each gym's merchant account
2. Progress tracking — weight, measurements, private photos, charts
3. Trainer permissions and screens — assigned members, workout and diet plans
4. Self-service freeze requests
5. Class schedule and booking
6. Offline kiosk — queue scans and sync when the internet returns
7. Fingerprint and face readers at the door, including turnstiles and door locks (§4.3)
8. Nepali language for the member app and staff dashboard
9. WhatsApp messages alongside SMS
10. Branded app store app per gym (React Native / Expo, one codebase) — sold as an add-on
11. Personal training packages and sessions tracking
12. Supplement / merchandise sales at the desk

---

## 15. Decisions

All of these can be changed later.

| Topic | Decision | What the build does now |
|---|---|---|
| **Name and domain** | **GymBhai**, `gymbhai.com` | Used in every URL, the member app and the code. Register the domain (and the Facebook / Instagram names) soon — it was free on 2026-09-19 |
| **SMS gateway** | Later | Built ready: one SMS interface, `console` provider for development, Sparrow and Aakash adapters ready. Choosing one is an environment setting plus the account's API key. The adapters follow the gateways' published APIs but have not been run against a live account: `python -m scripts.sms_check` reads the account's credit balance before anything is sent (docs/DEPLOY.md §5). Sparrow (checked against docs.sparrowsms.com on 2026-09-20) also whitelists the caller's IP address and queues without giving a message id, so there is no delivery report to record |
| **Pricing** | Later | Plans with us are rows edited in `/admin`, never hard-coded; the trial works without any price set |
| **Door hardware** | Later — maybe fingerprint or face | v1 ships QR (kiosk, staff phone, USB scanner, manual). The check-in service accepts other sources, so fingerprint / face readers plug in later (§4.3) |
| **Language** | English only at launch | All text in translation files so Nepali can be added later without redoing screens |
| **Calendar** | Each gym chooses | AD or BS for counting plans; AD, BS or both for showing dates (§5.1) |
| **Staff** | Owner decides per person | Staff accounts with ticked permissions and branches, including approving app payments (§2.1) |
