# Pilot: onboarding the first gyms

PLAN.md §12, M5: onboard 2–3 pilot gyms, import their registers, fix what
they hit. This is the checklist for each gym, and how to collect what they hit.

## Before the visit

- [ ] The gym's name, the owner's mobile number, and whether they count
      months in **AD or BS** — ask; there is no default (PLAN.md §5.1).
- [ ] Their register: an Excel sheet or a photo of the book. At least name,
      mobile number and expiry date per member.
- [ ] Their plans and prices, and admission fee if any.
- [ ] A photo of each payment QR they use (eSewa, Khalti, Fonepay, bank).
- [ ] SMS credits: the trial includes 50. A register import sends nothing;
      welcome SMS go out only when they choose.

## At the gym (about an hour)

1. **Sign up** together at `/signup` on the owner's phone: gym name, address
   (`app.gymbhai.com/<slug>`), calendar choice, owner's mobile.
2. **Settings → Plans:** set prices on the four starting plans; hide any they
   don't sell; add their own (e.g. "Morning only — 3 months").
3. **Settings → Your payment accounts:** add each account and upload its QR.
4. **Import / export → Import your register.** Check the column matches, fix
   the rows it lists (usually missing or landline numbers), import.
5. **Staff:** add each desk person with the *Front desk* starting point, and
   a manager with *Manager* if they have one. Tick branches if they have more
   than one.
6. **Door:** on the tablet at the entrance, sign in as the owner, open
   `/kiosk`, choose *Use this device as the door scanner*. Mount it at face
   height, camera towards the members.
7. **Print the QR poster** (Settings → Door scanners → Print QR poster) and
   put it by the door and the desk.
8. **Members without smartphones:** print their cards from their profile.
9. **Try the whole loop** with one real member: sell a renewal at the desk,
   they sign in on their phone, scan at the kiosk.
10. When the owner is ready: **Resend welcome** to members, a few at a time,
    so the desk isn't swamped with "what is this SMS?"

## After

- [ ] Day 2: call the owner. Did the desk use it? Did the door let the right
      people in?
- [ ] Week 1: check `/admin` for their SMS balance and active members.
- [ ] Before the trial ends: talk pricing; they pay from Settings →
      Subscription; approve it in `/admin`.

## Collecting what they hit

Keep one list per gym, and for each problem write down: what they were
doing, what they expected, what happened, and the screen (a photo is fine).
Fix the ones that stop the desk or the door first; everything else waits for
the next weekly update (docs/DEPLOY.md §6).
