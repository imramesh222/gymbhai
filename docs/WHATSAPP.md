# WhatsApp messages: going live

GymBhai sends reminders and answers by WhatsApp, between push (free) and SMS
(PLAN.md §19.3). The code is built and tested against a stand-in `console`
provider that writes each message to the log. These steps make it real.
Meta's checks take days to weeks, so start them early.

| What | Where in the code |
|---|---|
| The templates (wording, English and Nepali) | `backend/app/core/whatsapp_templates.py` |
| Sending, credits, falling back to SMS, the webhook | `backend/app/services/whatsapp/` |
| Meta's webhook | `POST /api/v1/whatsapp/webhook` (`backend/app/api/routes/whatsapp.py`) |
| Printing and submitting the templates | `python -m scripts.whatsapp_templates` |

## 1. Meta's side (outside the code)

1. **A Meta business for GymBhai**, verified: business.facebook.com →
   Security Centre → *Start verification*. It needs the company's registration
   documents, and the website (`gymbhai.com`) should name the company.
2. **A WhatsApp Business Account and app**: developers.facebook.com → *Create
   app* → *Business* → add the *WhatsApp* product, linked to that business.
3. **A phone number not already on WhatsApp** (a new SIM, or a landline that
   can take a call or SMS for the code). Add it under WhatsApp → *API Setup*.
   Its **display name** ("GymBhai") is reviewed separately; messages show
   that name.
4. **A payment method** on the WhatsApp Business Account (WhatsApp Manager →
   *Payment settings*). Check Nepal's price for *utility* messages on Meta's
   own rate card; PLAN.md §19.3 has the figure we planned with.
5. **A System User and a permanent token**: Business Settings → *System
   users* → add one (Admin), give it the app and the WhatsApp Business Account
   with *Full control*, then *Generate token* with
   `whatsapp_business_messaging` and `whatsapp_business_management`. Keep it
   somewhere safe: it's shown once.

Note down: the **phone number id** (API Setup, not the number itself), the
**WhatsApp Business Account id**, the **app secret** (App settings → Basic),
and the token.

## 2. The server

In `.env.prod`:

```sh
WHATSAPP_PROVIDER=meta
WHATSAPP_TOKEN=<the System User's token>
WHATSAPP_PHONE_NUMBER_ID=<the number's id>
WHATSAPP_APP_SECRET=<the app secret>
WHATSAPP_VERIFY_TOKEN=<any long random string you choose>
PUBLIC_APP_URL=https://app.gymbhai.com   # the buttons' links start here
```

`WHATSAPP_API_VERSION` defaults to `v21.0`; set it to the version your Meta app
uses. The API refuses to start with `meta` and any of the four missing.

## 3. The templates

WhatsApp only sends a business's first message from a template Meta approved,
so the gyms' own SMS wording can't go by WhatsApp. Ours are all in Meta's
*utility* category: membership ending or ended, active until, money owed (a
membership and personal training), personal training ending, a payment not
confirmed, a freeze answered, the welcome and a receipt. Win-back, birthday,
not visiting and notices are marketing in Meta's terms, cost several times as
much, and stay push then SMS.

```sh
docker compose exec api python -m scripts.whatsapp_templates            # look first
docker compose exec api python -m scripts.whatsapp_templates --create --waba <WABA id>
```

Each is reviewed separately, usually within a day; WhatsApp Manager →
*Message templates* shows where each stands. A rejected one: change the
wording in `whatsapp_templates.py`, keep to the rules its tests check, give it
a new key (Meta won't take the same name again for a while), and submit
again.

**Nepali.** Meta's template languages don't include Nepali. Our Nepali
wording is submitted under Hindi (`hi`), which shares the script
(`WHATSAPP_NEPALI_LANGUAGE`). If Meta refuses it there, set
`WHATSAPP_NEPALI_LANGUAGE=` (empty): members who use the app in Nepali then
get the English templates.

## 4. The webhook

developers.facebook.com → your app → WhatsApp → *Configuration* → Webhook:

- Callback URL: `https://app.gymbhai.com/api/v1/whatsapp/webhook`
- Verify token: the `WHATSAPP_VERIFY_TOKEN` above

Then *Manage* → subscribe to **messages**. Meta checks the address at once
(GET with the verify token). From then on it POSTs, signed with the app
secret, every delivery report (delivered, read, failed) and every message a
member writes to our number. Anything not signed with our secret is refused.

## 5. Try it

1. Send yourself a template, from a number you've agreed with:
   ```sh
   docker compose exec api python -m scripts.whatsapp_templates --send-test 98XXXXXXXX
   ```
2. In `/admin` → Plans → *Message prices*, set what one WhatsApp message costs
   a gym, in message credits (an SMS part is 1).
3. In a test gym: Settings → Gym → *Send messages by WhatsApp*, a member with
   *Agrees to messages on WhatsApp* ticked and no app notifications, and a
   receipt → *Send on WhatsApp*. Messages → Sent messages shows it go, then
   *Delivered* and *Read* as Meta reports them.
4. Reply to it from the phone: you get one answer a day saying where to reach
   the gym. Reply `STOP`: WhatsApp turns off for that number at every gym, and
   their next message goes by SMS.
5. Send to a number that isn't on WhatsApp: it fails, the SMS goes instead,
   the credit comes back, and that number isn't tried by WhatsApp for 30 days.

## What it costs and who pays

Gyms pay in message credits, one balance with SMS (PLAN.md §19.3): charged
when Meta takes a message, given back when Meta reports it failed. Our
answers to members who write in are on us; Meta charges us for them.
