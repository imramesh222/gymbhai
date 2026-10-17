/**
 * The terms of service and the privacy policy, in English (PLAN.md §16.1).
 *
 * Long-form text lives here rather than in en.json: Nepali later is a
 * legal.ne.ts beside it. The date matches TERMS_VERSION in
 * backend/app/core/legal.py, which records what each gym accepted; change
 * both together, and a lawyer reads every change before it goes live.
 */

export interface LegalSection {
  heading: string;
  paragraphs?: string[];
  bullets?: string[];
}

export interface LegalDocument {
  title: string;
  updated: string;
  intro: string;
  sections: LegalSection[];
}

export const LEGAL_VERSION = "2026-10-17";
export const CONTACT_EMAIL = "support@gymbhai.com";

export const terms: LegalDocument = {
  title: "Terms of service",
  updated: "17 October 2026",
  intro:
    "These terms are between GymBhai (“we”) and the gym that signs up (“you”). By creating a gym account, the owner accepts them for the gym.",
  sections: [
    {
      heading: "1. What GymBhai is",
      paragraphs: [
        "GymBhai is software for running a gym: members, memberships, records of payments, check-ins at the door, SMS to members and an app for your members. We provide it online, and we keep improving it.",
      ],
    },
    {
      heading: "2. Your account",
      bullets: [
        "The person who signs up is the gym's owner. The owner adds staff and decides what each of them may do.",
        "Keep passwords to yourselves, and turn on two-step sign-in. You are responsible for what is done with your gym's accounts.",
        `Tell us straight away at ${CONTACT_EMAIL} if you think an account has been misused.`,
      ],
    },
    {
      heading: "3. Money between you and your members",
      paragraphs: [
        "We never handle payments between you and your members. Members pay you directly, in cash or to your own eSewa, Khalti, Fonepay or bank account; GymBhai records what you enter. Receipts from GymBhai are payment receipts, not tax (VAT) invoices. Your taxes are yours to take care of.",
      ],
    },
    {
      heading: "4. Paying for GymBhai",
      bullets: [
        "Every gym starts with a 14-day free trial. We don't ask for payment details for it.",
        "After the trial you pay for the plan you choose, at the price shown in GymBhai when you pay. We give 30 days' notice of a price change, and it applies from your next payment.",
        "If a payment is late you have 7 more days. After that your dashboard becomes read-only until you pay: you can still see and export everything, and your members' app and check-in at the door keep working.",
        "SMS credits are bought separately and one is used for each SMS part sent. Unused credits are not refunded, but they don't expire while you use GymBhai.",
      ],
    },
    {
      heading: "5. Your data",
      paragraphs: [
        "Everything you and your members put into GymBhai belongs to your gym. You can download it to Excel at any time. We use it only to provide GymBhai to you, as the privacy policy explains.",
      ],
    },
    {
      heading: "6. Your members' details",
      bullets: [
        "You decide what you record about your members. You are responsible for being allowed to record it, and for telling them how it is used; you can point them to our privacy policy.",
        "When a member is entitled to have their details removed, use Erase member, which removes them for good.",
        "Add members under 18 only with a parent's or guardian's agreement.",
      ],
    },
    {
      heading: "7. Using GymBhai properly",
      paragraphs: ["You must not:"],
      bullets: [
        "send spam, or SMS that aren't about your members' gym membership;",
        "use GymBhai for anything unlawful;",
        "try to reach another gym's data, or to break, overload or get round GymBhai's security;",
        "resell GymBhai without our written agreement.",
      ],
    },
    {
      heading: "8. Suspension and leaving",
      bullets: [
        "You can stop using GymBhai at any time. Export your data first.",
        "We may suspend a gym that breaks these terms. We tell you first, unless we must act at once to protect others.",
        "When a gym leaves, we keep its data for 90 days so it can come back or export it, then delete it. Copies in our backups are gone within 30 days after that.",
      ],
    },
    {
      heading: "9. Keeping it running",
      paragraphs: [
        "We work to keep GymBhai available and your data safe, with continuous backups and encrypted connections. We can't promise it will never be interrupted, and we may change or improve its features.",
      ],
    },
    {
      heading: "10. Liability",
      paragraphs: [
        "GymBhai is provided as it is. As far as the law allows, we are not liable for indirect losses, such as lost profits or lost members, and our total liability in any year is limited to what you paid us in the 12 months before. Nothing here limits a liability that the law doesn't allow to be limited.",
      ],
    },
    {
      heading: "11. Changes to these terms",
      paragraphs: [
        "We may update these terms. We tell gym owners in GymBhai at least 30 days before a change that matters takes effect; using GymBhai after that means accepting it.",
      ],
    },
    {
      heading: "12. Law",
      paragraphs: [
        "These terms are governed by the laws of Nepal, and the courts of Kathmandu decide any dispute.",
      ],
    },
    {
      heading: "13. Contact",
      paragraphs: [`Questions about these terms: ${CONTACT_EMAIL}.`],
    },
  ],
};

export const privacy: LegalDocument = {
  title: "Privacy policy",
  updated: "17 October 2026",
  intro:
    "This explains what GymBhai holds about people, why, and what they can ask for. It covers gym owners and staff, and the members of gyms that use GymBhai.",
  sections: [
    {
      heading: "1. Who is responsible",
      paragraphs: [
        "A member's details are entered by their gym. The gym decides what to record and why, and is responsible for that data; GymBhai handles it on the gym's behalf. For the accounts of gym owners and staff, GymBhai is responsible. We follow Nepal's Individual Privacy Act, 2075 (2018).",
      ],
    },
    {
      heading: "2. What we hold",
      bullets: [
        "Gym owners and staff: name, mobile number and email, the password (stored only in a form that can't be turned back into it), sign-ins, the devices signed in with their internet addresses, and what each person did in the dashboard.",
        "Members, as their gym enters them: name and mobile number, and where the gym records them, email, gender, date of birth, address, emergency contact, photo and notes. Also their memberships, payments, visits, the SMS sent to them and the payment screenshots they send from the app.",
        "From the member app: the devices a member is signed in on.",
        "Technical records: internet addresses and error reports, to keep GymBhai secure and working.",
      ],
    },
    {
      heading: "3. What it is used for",
      bullets: [
        "Running GymBhai for the gym: memberships, check-in at the door, receipts, reminders and notices by SMS, and the member app.",
        "Keeping accounts safe: limits on sign-in attempts, two-step sign-in and a record of every change.",
        "Billing gyms for GymBhai, and fixing problems.",
      ],
      paragraphs: [
        "We don't sell personal data, don't show advertising, and don't use members' details for our own marketing.",
      ],
    },
    {
      heading: "4. Who else handles it",
      paragraphs: [
        "Only the services GymBhai needs in order to run, and only for that: our hosting and storage providers (including Cloudflare R2, for photos and backups), SMS gateways that deliver messages (such as Sparrow SMS or Aakash SMS), an email provider for sign-in codes, and an error-reporting service that receives no form contents. We disclose data when the law of Nepal requires it.",
      ],
    },
    {
      heading: "5. How long it is kept",
      bullets: [
        "For as long as the gym uses GymBhai.",
        "Sign-in codes and records of sign-in attempts: a day. Answers kept to stop a payment being saved twice: a day.",
        "Backups: up to 30 days.",
        "When a gym leaves: 90 days, so it can come back or export its data, then deleted.",
      ],
    },
    {
      heading: "6. Keeping it safe",
      paragraphs: [
        "Encrypted connections, passwords stored only in a one-way form, two-step sign-in, each gym's data kept apart from every other gym's, limits on guessing passwords and codes, and a record of every change.",
      ],
    },
    {
      heading: "7. What members can ask for",
      paragraphs: [
        "A member can ask their gym to show them, correct or erase their details. Erasing removes their name, contact details, date of birth, address, photo and notes for good; the gym keeps their memberships, payments and visits for its accounts, without their name. Members can also write to us, and we pass the request to their gym.",
      ],
    },
    {
      heading: "8. Changes",
      paragraphs: [
        "When this policy changes, the date at the top changes too, and we tell gym owners in GymBhai about anything significant.",
      ],
    },
    {
      heading: "9. Contact",
      paragraphs: [`Questions about privacy: ${CONTACT_EMAIL}.`],
    },
  ],
};
