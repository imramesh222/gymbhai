import { type Page } from "@playwright/test";

import { expect, test } from "./fixtures";
import { OTP, priceOneMonthPlan, randomDigits, signUpGym } from "./helpers";

async function scanAtKiosk(kiosk: Page, code: string) {
  // The kiosk's hidden input is where a USB scanner types; it stays focused.
  const input = kiosk.getByLabel("Scanner input");
  await input.fill(code);
  await input.press("Enter");
}

/**
 * PLAN.md §13, the one flow that must never break:
 * add member -> take payment -> member signs in -> scans QR at kiosk ->
 * allowed; membership ends -> scan denied.
 */
test("the flow that must never break", async ({ browser }) => {
  // The owner's desk.
  const desk = await (await browser.newContext()).newPage();
  const gym = await signUpGym(desk, "AD");
  await priceOneMonthPlan(desk, "1500");

  // Add member -> take payment.
  const phone = `98${randomDigits(8)}`;
  await desk.goto("/staff/members/new");
  await desk.getByLabel("Full name").fill("Sita Rai");
  await desk.getByLabel("Mobile number").fill(phone);
  await desk.getByLabel("Plan").selectOption({ label: "1 month — Rs 1,500" });
  await desk.getByRole("button", { name: "Save member" }).click();
  await expect(desk.getByRole("link", { name: "Print receipt" })).toBeVisible();
  const memberUrl = desk.url().split("?")[0];

  // Register this browser as the door scanner, then open the kiosk.
  await desk.goto("/kiosk");
  await desk
    .getByRole("button", { name: /Use this device as the door scanner/ })
    .click();
  const kiosk = desk;
  await expect(kiosk.getByText("Show your QR code to the camera")).toBeVisible();

  // The member signs in on their own phone.
  const phoneCtx = await browser.newContext();
  // Headless Chromium always says notifications are "denied"; a phone that
  // was never asked says "default".
  await phoneCtx.addInitScript(() =>
    Object.defineProperty(Notification, "permission", { get: () => "default" }),
  );
  const app = await phoneCtx.newPage();
  await app.goto(`/${gym.slug}`);
  await app.getByLabel("Mobile number or email").fill(phone);
  await app.getByRole("button", { name: "Send me a code" }).click();
  await app.getByLabel("Code").fill(OTP);
  await app.getByRole("button", { name: "Sign in" }).click();
  await expect(app.getByText("Show this at the door")).toBeVisible();
  await expect(app.getByText("days left", { exact: true })).toBeVisible();
  // Offered once, put away with "Not now"; it stays in Profile (§16.3, 8.3).
  const prompt = app.getByRole("region", { name: "Get reminders on this phone" });
  await expect(prompt).toBeVisible();
  await prompt.getByRole("button", { name: "Not now" }).click();
  await expect(prompt).toHaveCount(0);
  const qr = app.getByRole("img", { name: "Your check-in QR code" });
  const code = await qr.getAttribute("data-qr-value");
  // Signed with Ed25519, which a kiosk can check offline (§19.2).
  expect(code).toMatch(/^gb2\./);

  // Scans the QR at the kiosk -> allowed.
  await scanAtKiosk(kiosk, code!);
  await expect(kiosk.getByText(/Welcome, Sita — \d+ days left/)).toBeVisible();

  // The membership ends: the desk moves its dates into the past.
  const staff = await (await browser.newContext({ storageState: undefined })).newPage();
  await staff.goto("/staff/login");
  await staff.getByLabel("Email or mobile number").fill(gym.phone);
  await staff.getByLabel("Password", { exact: true }).fill("correct-horse-battery");
  await staff.getByRole("button", { name: "Sign in" }).click();
  await staff.waitForURL("**/staff");
  await staff.goto(memberUrl);
  await staff.getByRole("tab", { name: /Memberships/ }).click();
  await staff.getByRole("link", { name: /1 month/ }).click();
  // The member page has an Edit button too: wait for the membership's.
  await staff.waitForURL("**/staff/memberships/**");
  await staff.getByRole("button", { name: "Edit", exact: true }).click();
  const dialog = staff.getByRole("dialog");
  const day = (offset: number) =>
    new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10);
  await dialog.getByLabel("Starts").fill(day(-40));
  await dialog.getByLabel("Ends (last day)").fill(day(-2));
  await dialog.getByLabel("Reason").fill("Test: membership ended");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(staff.getByText("Expired").first()).toBeVisible();

  // -> scan denied, and the card says so in red.
  await kiosk.waitForTimeout(3500); // the last result card clears after 3 s
  const fresh = await qr.getAttribute("data-qr-value");
  await scanAtKiosk(kiosk, fresh!);
  await expect(
    kiosk.getByText(/Membership expired on .* — please see the desk/),
  ).toBeVisible();

  // The member's app still opens, and shows the truth.
  await app.reload();
  await expect(app.getByText("Expired")).toBeVisible();
});

test("renew from the app, approve at the desk", async ({ browser }) => {
  const desk = await (await browser.newContext()).newPage();
  const gym = await signUpGym(desk, "AD");
  await priceOneMonthPlan(desk, "1500");
  await desk.goto("/staff/settings/payment-accounts");
  await desk
    .locator("section", { hasText: "Your payment accounts" })
    .getByRole("button", { name: "Add", exact: true })
    .click();
  await desk.getByRole("dialog").getByRole("button", { name: "Save" }).click();
  // Wait for it to be saved: leaving the page at once can cancel the request.
  await expect(
    desk
      .locator("section", { hasText: "Your payment accounts" })
      .getByText("Upload QR"),
  ).toBeVisible();

  const phone = `98${randomDigits(8)}`;
  await desk.goto("/staff/members/new");
  await desk.getByLabel("Full name").fill("Hari Thapa");
  await desk.getByLabel("Mobile number").fill(phone);
  await desk.getByLabel("Sell a membership now").uncheck();
  await desk.getByRole("button", { name: "Save member" }).click();
  await expect(desk.getByRole("heading", { name: /Hari Thapa/ })).toBeVisible();

  const app = await (await browser.newContext()).newPage();
  await app.goto(`/${gym.slug}`);
  await app.getByLabel("Mobile number or email").fill(phone);
  await app.getByRole("button", { name: "Send me a code" }).click();
  await app.getByLabel("Code").fill(OTP);
  await app.getByRole("button", { name: "Sign in" }).click();
  // Their own details: an emergency contact (§16.3, 8.5).
  await app.getByRole("link", { name: "Me", exact: true }).click();
  await app.getByLabel("Emergency contact").fill("Gita Thapa 9811111111");
  await app.getByRole("button", { name: "Save" }).click();
  await expect(app.getByText("Saved.")).toBeVisible();

  await app.getByRole("link", { name: "Renew" }).first().click();
  // Nothing is chosen for them: the bar waits for a plan, then a way to pay.
  await expect(app.getByRole("button", { name: "Choose a plan" })).toBeDisabled();
  await app.getByText("1 month").click();
  await expect(app.getByRole("radio", { name: "1 month, Rs 1,500" })).toBeChecked();
  await expect(app.getByRole("button", { name: "Choose how to pay" })).toBeDisabled();
  await app.getByText("eSewa", { exact: true }).click();
  // Proof first: nothing is sent without it.
  await app.getByRole("button", { name: "I've paid" }).click();
  await expect(
    app.getByText("Enter the transaction ID or add a screenshot."),
  ).toBeVisible();
  await app.getByLabel("Transaction ID").fill(`ES-${randomDigits(6)}`);
  await app.getByRole("button", { name: "I've paid" }).click();
  await expect(app.getByText("Sent — waiting for the gym to confirm")).toBeVisible();

  await desk.goto("/staff/payment-requests");
  await expect(desk.getByText(/Hari Thapa/)).toBeVisible();
  await desk.getByRole("button", { name: "Approve" }).click();
  await desk.getByRole("dialog").getByRole("button", { name: "Approve" }).click();
  await expect(desk.getByText("Nothing waiting.")).toBeVisible();

  await app.goto(`/${gym.slug}`);
  await expect(app.getByText("days left", { exact: true })).toBeVisible();

  // Going away: ask to freeze, the desk approves (§16.3, 8.6).
  await app.getByRole("link", { name: /Ask to freeze/ }).click();
  await app.getByLabel(/^Why/).fill("Home for Dashain");
  await app.getByRole("button", { name: "Ask the gym" }).click();
  await expect(app.getByText("Waiting for the gym to answer")).toBeVisible();

  await desk.goto("/staff/freeze-requests");
  await expect(desk.getByText("“Home for Dashain”")).toBeVisible();
  await desk.getByRole("button", { name: "Approve" }).click();
  await desk.getByRole("dialog").getByRole("button", { name: "Approve" }).click();
  await expect(desk.getByText(/membership is frozen/)).toBeVisible();

  // The member's screen follows by itself.
  await expect(app.getByText(/^Frozen from/)).toBeVisible();
});
