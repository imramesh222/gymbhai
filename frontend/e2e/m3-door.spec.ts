import { expect, test, type Page } from "@playwright/test";

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
  const app = await phoneCtx.newPage();
  await app.goto(`/${gym.slug}`);
  await app.getByLabel("Mobile number or email").fill(phone);
  await app.getByRole("button", { name: "Send me a code" }).click();
  await app.getByLabel("Code").fill(OTP);
  await app.getByRole("button", { name: "Sign in" }).click();
  await expect(app.getByText("Show this at the door")).toBeVisible();
  await expect(app.getByText("days left", { exact: true })).toBeVisible();
  const qr = app.getByRole("img", { name: "Your check-in QR code" });
  const code = await qr.getAttribute("data-qr-value");
  expect(code).toMatch(/^gb1\./);

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
  await desk.goto("/staff/settings");
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
  await app.getByRole("link", { name: "Renew" }).first().click();
  await app.getByText("1 month").click();
  await app.getByRole("button", { name: "eSewa" }).click();
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
});
