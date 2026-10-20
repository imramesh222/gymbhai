import { expect, test } from "./fixtures";
import { memberSignsIn, priceOneMonthPlan, randomDigits, signUpGym } from "./helpers";

/**
 * PLAN.md §20.2: the gym's eSewa merchant keys in Settings, then a member
 * renewing from the app through the wallet (the console wallet stands in for
 * eSewa), the membership starting by itself with nobody at the desk.
 */
test("a payment the wallet confirms renews with nobody at the desk", async ({
  browser,
}) => {
  const desk = await (await browser.newContext()).newPage();
  const gym = await signUpGym(desk, "AD");
  await priceOneMonthPlan(desk, "1500");
  await desk.goto("/staff/settings/payment-accounts");
  const accounts = desk.locator("section", { hasText: "Your payment accounts" });
  await accounts.getByRole("button", { name: "Add", exact: true }).click();
  await desk.getByRole("dialog").getByRole("button", { name: "Save" }).click();
  await accounts.getByRole("button", { name: "Confirm automatically" }).click();
  const keys = desk.getByRole("dialog", { name: /eSewa: confirm payments/ });
  await keys.getByLabel("Merchant code (product code)").fill("EPAYTEST");
  await keys.getByLabel("Secret key").fill("8gBm/:&EnhH.1/q");
  await keys.getByRole("button", { name: "Save" }).click();
  await expect(accounts.getByText("Payments confirmed by eSewa")).toBeVisible();
  await expect(accounts.getByText("Secret key ending .1/q")).toBeVisible();

  const phone = `98${randomDigits(8)}`;
  await desk.goto("/staff/members/new");
  await desk.getByLabel("Full name").fill("Hari Thapa");
  await desk.getByLabel("Mobile number").fill(phone);
  await desk.getByLabel("Sell a membership now").uncheck();
  await desk.getByRole("button", { name: "Save member" }).click();
  await expect(desk.getByRole("heading", { name: /Hari Thapa/ })).toBeVisible();

  const app = await memberSignsIn(browser, gym.slug, phone);
  await app.getByRole("link", { name: "Renew" }).first().click();
  await app.getByText("1 month").click();
  await app.getByText("eSewa", { exact: true }).click();
  await expect(app.getByText("CONFIRMED INSTANTLY")).toBeVisible();
  // No transaction ID to type: the wallet says.
  await expect(app.getByLabel("Transaction ID")).toHaveCount(0);
  await app.getByRole("button", { name: "Pay with eSewa" }).click();

  // The pretend eSewa, on our own page.
  await app.waitForURL("**/pay/**");
  await expect(app.getByText(/A pretend eSewa/)).toBeVisible();
  await app.getByRole("button", { name: "Pay", exact: true }).click();
  await expect(app.getByText("Paid. Your membership is renewed.")).toBeVisible();
  await app.getByRole("link", { name: /Back to/ }).click();
  await expect(app.getByText("days left", { exact: true })).toBeVisible();

  // Nothing for the desk to approve; the payment is there, from eSewa.
  await desk.goto("/staff/payment-requests");
  await expect(desk.getByText("Nothing waiting.")).toBeVisible();
  await desk.goto("/staff/payments");
  await expect(desk.getByText("Hari Thapa").first()).toBeVisible();
});
