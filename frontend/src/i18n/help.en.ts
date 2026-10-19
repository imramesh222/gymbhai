/**
 * Short how-to guides for gym staff, in English (PLAN.md §16.5, 10.3).
 *
 * Long-form text lives here rather than in en.json: Nepali later is a
 * help.ne.ts beside it. Keep each guide to the steps someone at the desk
 * needs, and the screen names exactly as the app shows them.
 */

export interface Guide {
  id: string;
  title: string;
  steps: string[];
  tip?: string;
}

export const guides: Guide[] = [
  {
    id: "add-member",
    title: "Add a member and take their first payment",
    steps: [
      "Open Members, then Add member (or press Ctrl K and type “add”).",
      "Type their name and mobile number. Take a photo: the desk checks it at the door.",
      "Leave “Sell a membership now” ticked, choose the plan, and check the price.",
      "Enter what they pay now, and how. Anything left is shown as owed.",
      "Save member. Print or share the receipt; they get an SMS with their app link.",
    ],
    tip: "Someone asked but didn't join today? Add them under Enquiries instead.",
  },
  {
    id: "renew",
    title: "Renew a membership",
    steps: [
      "Find the member (Ctrl K, or Members) and open them.",
      "Press Renew. The new membership starts the day after the current one ends.",
      "Choose the plan, enter the payment and save.",
    ],
  },
  {
    id: "door",
    title: "Set up the door scanner",
    steps: [
      "On a tablet or old phone at the door, sign in as the owner and open /kiosk.",
      "Choose “Use this device as the door scanner” for your branch.",
      "Members show the QR in their app (or on their printed card) to its camera.",
      "Print the QR poster from Settings › Door so members can open their app.",
    ],
    tip: "No internet at the door? Check members in from Door on any staff phone.",
  },
  {
    id: "payment-requests",
    title: "Approve payments members send from the app",
    steps: [
      "Members pay your eSewa, Khalti or bank QR, then send the transaction ID.",
      "Open Payment requests (the red number shows how many are waiting).",
      "Check the money arrived in your own wallet or bank app.",
      "Approve, or Reject with a reason the member will see.",
    ],
  },
  {
    id: "import",
    title: "Bring in your existing register",
    steps: [
      "Open Data › Import your register, and choose your Excel or CSV file.",
      "Match the columns: name, mobile number, plan, expiry date (AD or BS).",
      "Check the preview: problems are shown row by row. Nothing is saved yet.",
      "Press Import. No SMS is sent to the people imported.",
    ],
  },
  {
    id: "follow-up",
    title: "Win back members who are drifting away",
    steps: [
      "Open Follow up: ending soon, lapsed, owe money and not visiting.",
      "Call, or Send message, from each row.",
      "Messages → Automations sends reminders for you every morning at 9.",
    ],
  },
  {
    id: "personal-training",
    title: "Sell personal training and record sessions",
    steps: [
      "Settings › Personal training: add your PT plans, monthly or a pack of sessions, with their prices.",
      "Staff › the trainer's account: tick “Train members”, or start from Trainer.",
      "Open the member, then Personal training › Sell personal training. Choose the plan and trainer, and take the payment.",
      "After each session the trainer opens Personal training › My clients and presses Record session.",
    ],
    tip: "Its money is its own: a membership's dues never include it, and its payments get their own receipts.",
  },
];
