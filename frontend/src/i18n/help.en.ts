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
  {
    id: "family-plans",
    title: "Sell a couple or family plan",
    steps: [
      "Settings › Plans and prices: make a plan such as “Couple — 1 year” and set People to 2 (up to 6 for a family). The price is for everyone together.",
      "Renew the person who pays, or Add member for them, and choose that plan.",
      "Under “Who else is on it?” find each of the others, or Add someone new (a child can share a parent's number).",
      "Take the payment as usual. Everyone gets their own membership and QR; the money is on the payer's.",
    ],
    tip: "A place still free? Open the payer's membership › On this plan › Add someone.",
  },
  {
    id: "classes",
    title: "Run classes with booking",
    steps: [
      "Settings › Classes: add each class (Zumba, yoga…) with its length and places.",
      "Add to the timetable: the day, time, branch and instructor. Classes are made 4 weeks ahead.",
      "Settings › Plans and prices: under “Classes it includes”, choose which classes each plan lets members book.",
      "Members book in their app. Classes in the Desk menu shows who's coming; Book a member books at the desk.",
      "The instructor opens My classes and ticks who came. Members who checked in at the door are ticked already.",
    ],
    tip: "Full? Members join the waitlist, and the first in line gets the place, with a notification, if someone cancels.",
  },
  {
    id: "progress",
    title: "Record a member's progress",
    steps: [
      "Open the member, then the Progress tab.",
      "Enter their height once, for BMI.",
      "Record a check: weight, and body fat or measurements if you take them.",
      "Members record their own in the app too, and see the chart of their weight.",
    ],
    tip: "Photos are private to the member. You see one only if they choose “Let my trainer see”, and they train with you.",
  },
  {
    id: "kiosk-offline",
    title: "When the internet drops at the door",
    steps: [
      "The door kiosk keeps a list of who may come in, and keeps letting them in with no internet.",
      "It shows an amber band and how many visits are waiting to be sent.",
      "When the internet is back, the visits are sent by themselves, at the times they happened.",
      "Settings › Check-in rules: “Kiosk works offline for (days)” sets how long it may decide by itself (3 days unless changed).",
    ],
    tip: "Open the kiosk once with internet after setting it up: it needs its first list.",
  },
  {
    id: "whatsapp",
    title: "Send reminders by WhatsApp",
    steps: [
      "Settings › Gym profile and calendar: tick “Send messages by WhatsApp”.",
      "On Add member or Edit, tick “Agrees to messages on WhatsApp” for members who say yes. Members can also turn it on in their app.",
      "Reminders and answers then go by WhatsApp to them when the app's notifications can't reach them, instead of SMS.",
      "Messages › Sent messages shows each one, and when it was delivered and read.",
    ],
    tip: "Each WhatsApp message uses message credits, like an SMS. Birthday and win-back messages stay notification, then SMS.",
  },
  {
    id: "shop",
    title: "Sell supplements and drinks at the desk",
    steps: [
      "Desk › Shop › Products: add what you sell, with its price. Tick “Count the stock” and say how many are on the shelf.",
      "Shop › Sell: tap each product into the basket (or scan its barcode), choose the member or leave it for a walk-in, and press “Sell and take the money”.",
      "The receipt is ready at once. The money shows in Payments and Today, and on Reports.",
      "When more arrives, Products › the product › Restock or count.",
    ],
    tip: "A mistake? Shop › Sales › Void this sale: the money is voided and the stock goes back.",
  },
  {
    id: "wallet-confirms",
    title: "Let eSewa, Khalti or Fonepay confirm app payments",
    steps: [
      "You need a merchant account with the wallet: ask eSewa, Khalti or Fonepay for one. It gives you a few keys.",
      "Settings › Payment accounts › your eSewa (or Khalti, or Fonepay) account › Confirm automatically. Type in the keys and save.",
      "Members who renew in the app now see “Pay with eSewa”. When eSewa confirms the money, their new membership starts by itself: nobody at the desk needs to approve it.",
      "If something changed since they paid (a new price, for example), the payment waits in Payment requests marked “Paid: confirmed by eSewa”: the money is already in your account.",
    ],
    tip: "To try it first, tick “Use the wallet's test system” with the wallet's test keys: nothing is sold. The wallet may charge you a small fee on each payment; GymBhai adds nothing.",
  },  {
    id: "own-app",
    title: "Your gym's own app in the Play Store and App Store",
    steps: [
      "Settings › Your own app: the app's name (as the stores show it), its colour and a square icon of at least 1024 × 1024 pixels. Press “Ask for my app”.",
      "Open an Apple Developer account and a Google Play developer account for your gym, and add GymBhai to them: Apple asks that your gym publishes its own app. We help with both.",
      "Pay the setup in Subscription. We build the app and send it to the stores; Settings › Your own app shows how far it has got.",
      "Once it's in the stores, your members see “Get the app” on their Home, with the store links.",
    ],
    tip: "Members already using the GymBhai app keep working there: nobody has to move.",
  },
];
