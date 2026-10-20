# Tax invoices for VAT-registered gyms

GymBhai can issue a VAT-registered gym's tax invoices and credit notes, keep
its sales book, and report each bill to IRD's Central Billing Monitoring
System (CBMS) (PLAN.md §20.4). **It is switched off on every server, and must
stay off until the Inland Revenue Department (IRD) has certified GymBhai.**

Under the Procedure Related to Computerized Invoicing, 2072, billing software
a taxpayer uses needs IRD's certification (the developer's obligation), and
the gym's tax office must approve its use (the gym's). Until both, a gym keeps
issuing its VAT bills as it does now. Settings → Tax says so.

| What | Where |
|---|---|
| The switch, per server | `TAX_INVOICES_CERTIFIED=true` (off by default; local and tests have it on) |
| Invoices, credit notes, numbering, CBMS | `backend/app/services/tax.py` |
| The gym's VAT registration, CBMS login | `backend/app/models/tax.py` (`gym_tax`), Settings → Tax |
| Where it hooks in | `memberships.record_payment`, `shop.sell` (invoices); `payments.void_payment`, `shop.void` (credit notes) |
| The PDF | `backend/app/services/receipts.py` (`_tax_page`) |
| The sales book | Reports (*VAT sales book*), `sales-book.xlsx`, `sales-returns.xlsx` |

## Before switching it on

1. **Certification.** Apply to IRD as the software's developer, with the
   company's registration. IRD reviews the software against its billing
   requirements and tests the CBMS connection; one source says it asks for the
   source code. Expect to change things after its review.
2. **An accountant reads it.** In particular, against the VAT Rules 2053 (rule
   17, schedule 5):
   - the invoice's contents and layout (`_tax_page`, `TaxDocumentView.tsx`);
   - prices including VAT: 13/113 of each payment is VAT, rounded to the paisa;
   - one invoice per payment, a part payment invoiced for what was paid;
   - a void as a credit note for the whole invoice, a refund as a credit note
     against the newest invoice on that membership with enough left;
   - the buyer's PAN (members have none here yet; sources say a buyer's
     details are needed from Rs 10,000, or when the buyer is VAT-registered).
3. **Hosting.** One source says a certified cloud system must keep its
   servers in Nepal, with IRD access. Ask IRD; it decides where GymBhai runs.
4. **The threshold.** Which gyms must use certified, real-time billing:
   sources say turnover over Rs 10 crore, 20 crore or 25 crore, and lower for
   some sectors. Most gyms are well below; they may still want proper
   invoices.
5. **CBMS.** IRD doesn't publish the API. `cbms_payload` follows community
   clients of it: `POST https://cbapi.ird.gov.np/api/bill` and
   `/api/billreturn`, amounts in rupees, dates in BS as `2083.07.03`, the
   fiscal year as `2083.084`, answers `200` (saved), `100` (credentials),
   `101` (already there), `102`/`103` (try again), `104` (a bad field),
   `105` (no such bill to return). Test with IRD's test login (`Test_CBMS`,
   PAN `999999999`) before any gym's, with `CBMS_PROVIDER=live`.

## How it behaves

- **Settings → Tax**: *We're registered for VAT*, the PAN (9 digits), and the
  day invoices start. Payments from that day get invoices; none before. The
  PAN can't change once invoices carry it.
- **Each payment** gets a tax invoice in the same transaction: numbered from
  1 in each fiscal year (from 1 Shrawan), with no gaps; the gym's name,
  address and PAN, and the buyer, copied as they were.
- **Never changed.** A payment's amount can't be edited once invoiced (void
  and record again). A void issues a credit note; a refund issues one against
  its invoice; voiding a refund issues a new invoice.
- **Copies.** The first print or PDF download is the original; each later one
  says *Copy of original (n)*. The desk's receipt page no longer fetches the
  PDF ahead for these, so opening it isn't a copy.
- **CBMS**: with the gym's login set, the worker sends each document as it's
  issued and retries while CBMS is down; refused ones show in Settings → Tax.

## Not built

Prices before VAT (VAT added at the desk); tax-exempt items; the abbreviated
tax invoice; invoices in Nepali; other taxes (excise, health service tax).
No help guide or What's new entry yet: they'd tell gyms about something
they can't turn on.
