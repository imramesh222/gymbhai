# App payments confirmed by the wallet: going live

A gym with its own eSewa, Khalti or Fonepay **merchant account** can let the
wallet confirm members' app payments, so a renewal starts with nobody at the
desk (PLAN.md §20.2). The money goes straight to the gym's merchant account;
GymBhai only asks the wallet whether it arrived.

The code is built and tested against a stand-in `console` wallet, a pretend
checkout on our own page. **None of the three wallets has been called yet,
not even their test systems.** These steps make it real, one wallet at a time.

| What | Where in the code |
|---|---|
| The three wallets (start a payment, check one) | `backend/app/services/gateways/providers.py` |
| Starting, checking, approving by itself | `backend/app/services/online_payments.py` |
| The member's routes and the checkout page's | `backend/app/api/routes/online_payments.py` |
| The keys, encrypted | `backend/app/core/sealed.py` (AES-GCM with `GATEWAY_KEY`) |
| The checkout page | `frontend/src/app/pay/[token]/` |
| Settings → Payment accounts → *Confirm automatically* | `frontend/src/components/settings/ListSections.tsx` |

## 1. The server

In `.env.prod`:

```
GATEWAY_PROVIDER=live
GATEWAY_KEY=<at least 32 random characters: openssl rand -base64 48>
```

`GATEWAY_KEY` encrypts every gym's merchant keys. Keep it with the other
secrets and back it up: if it's lost or changed, every gym must enter its keys
again (Settings shows *The keys can't be read*). Until `GATEWAY_PROVIDER=live`,
the feature stays off on a server: gyms don't see *Confirm automatically*.

`form-action` in the Content-Security-Policy (`frontend/src/lib/csp.ts`)
already allows eSewa's two checkout hosts. Khalti and Fonepay need nothing
there: Khalti is a redirect, Fonepay a QR.

## Trying it on your Mac and a phone

Locally `GATEWAY_PROVIDER` is `console`: *Pay … with Khalti* opens **our own
pretend wallet** (Pay / Cancel buttons), never Khalti's page. That's enough to
try the flow end to end.

On a phone, first run `make mobile-env`. The checkout is a page on the web app,
reached by a link the API makes from `PUBLIC_APP_URL`; left at its default,
`http://localhost:3000`, the phone's browser looks for it on the phone itself
and opens nothing. `make mobile-env` sets it to this Mac's Wi-Fi address (the
phone must be on the same Wi-Fi) and restarts the API. The wallet sends the
browser back to that same address after paying, so it matters for a real test
too.

To see the wallet's own page, with its test money, in `.env`:

```
GATEWAY_PROVIDER=live
GATEWAY_KEY=<at least 32 random characters: openssl rand -base64 48>
```

then `docker compose up -d --force-recreate api worker`, and in Settings →
Payment accounts enter the wallet's **test** keys again (keys saved before
`GATEWAY_KEY` was set can't be read) with *Use the wallet's test system*
ticked. For Khalti, its test page signs in with Khalti's own test accounts
(see docs.khalti.com). Khalti's checkout is a web page: it may offer to open
the Khalti app, but it doesn't have to.

## 2. Each wallet, with its test system first

Each account in Settings has *Use the wallet's test system*. On it, payments
are the wallet's pretend money and **nothing is sold**: the member sees
"…'s test system confirmed it. Nothing was sold", and no request, payment or
membership is made. Use it with the wallet's published test keys, from a
member record of your own, before a gym's real keys.

### eSewa (ePay v2)

- Test keys (public, from eSewa's developer documents): merchant code
  `EPAYTEST`, secret key `8gBm/:&EnhH.1/q`. eSewa's test wallet logins are on
  developer.esewa.com.np.
- Real keys: the gym asks eSewa for an **ePay merchant account**; eSewa gives
  a merchant code (product code) and a secret key.
- What we do: a form signed with HMAC-SHA256 over
  `total_amount,transaction_uuid,product_code`, posted to
  `rc-epay.esewa.com.np` (test) or `epay.esewa.com.np`; then
  `GET …/api/epay/transaction/status/` on `rc.esewa.com.np` or `esewa.com.np`.
  `COMPLETE` is paid; `CANCELED` and refunds are not; anything else is asked
  again.
- To check on the first real try: that eSewa takes `total_amount` without
  decimals ("1500"), and that the signature is accepted.

### Khalti (Web Checkout, KPG-2)

- Test keys: a merchant account at test-admin.khalti.com gives a test secret
  key.
- Real keys: the gym's merchant account at admin.khalti.com → *Keys* → the
  **live secret key**.
- What we do: `POST /api/v2/epayment/initiate/` (amount in paisa) on
  `dev.khalti.com` (test) or `khalti.com`, sending the member to the
  `payment_url`; then `POST /api/v2/epayment/lookup/` with the `pidx`.
  `Completed` is paid; `Expired`, `User canceled` and refunds are not.
- To check: that a gym's `website_url` (our domain) is accepted, and the
  phone number format in `customer_info`.

### Fonepay (dynamic QR)

**Fonepay gives its API documents to merchants only.** The adapter follows
published write-ups of the dynamic QR API: `POST
/merchant/merchantDetailsForThirdParty/thirdPartyDynamicQrDownload` with an
HMAC-SHA512 (lowercase hex) over `amount,prn,merchantCode,remarks1,remarks2`,
then `…/thirdPartyDynamicQrGetStatus` over `prn,merchantCode`. Before any gym
turns Fonepay on:

1. Get Fonepay's own documents with the first gym's merchant account.
2. Check the hosts in `Fonepay.BASE` (the test host differs between write-ups:
   `dev-merchantapi.fonepay.com` here), the field names, the signature order,
   and the status values (`success`, `failed`, `pending`).
3. Try it on Fonepay's test system, then once with real money.

## 3. Turning it on for a gym

1. The gym's eSewa, Khalti or Fonepay account is in Settings → Payment
   accounts (it already is, if members pay its QR).
2. *Confirm automatically* → the keys the wallet gave the gym → Save. Only
   staff with *Set up payment methods* can do it; the keys are never shown
   again (the last four characters are, to recognise them).
3. If the wallet refuses the keys, the account says so in red in Settings,
   and members see "This wallet isn't set up right at the gym".

## 4. How it behaves

- The member picks a plan, then *Pay Rs 1,500 with eSewa*. The amount is the
  server's (the plan's price and any admission fee). There's no part payment.
- The wallet's page, then back to `/pay/<link>/back`, which asks the wallet.
  The worker also asks, after 1, 1, 2, 3, 5… minutes, for two hours, for the
  member who closes the page. A wallet that can't be reached never expires a
  payment early: it's asked for another day.
- Paid: a payment request approved by itself, so the membership is sold
  exactly as an approval at the desk would sell it; *Received by* is empty and
  the payment's note says *confirmed by eSewa*. The activity log has it as
  done by GymBhai (`actor_type` system).
- Paid, but something changed (the plan's price, someone left a family plan,
  the member had started a second payment): the request waits on Payment
  requests marked **Paid: confirmed by eSewa**, for the desk to approve.
- Phone app: the checkout opens in the phone's browser (`pay_url`) and comes
  back to the app with `gymbhai://renew`; the approval arrives live.
