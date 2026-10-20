import { expect, test } from "./fixtures";
import { memberSignsIn, priceOneMonthPlan, randomDigits, signUpGym } from "./helpers";

/**
 * PLAN.md §19.3: WhatsApp turned on, a member who agrees, their welcome on
 * WhatsApp (the console provider stands in for Meta), a receipt sent there,
 * and the member's own switch in the app.
 */
test("WhatsApp messages: the welcome and a receipt, and the member's say", async ({
  page,
  browser,
}) => {
  const gym = await signUpGym(page, "AD");
  await priceOneMonthPlan(page, "1500");
  await page.goto("/staff/settings");
  await page.getByLabel("Send messages by WhatsApp").check();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();

  const phone = `98${randomDigits(8)}`;
  await page.goto("/staff/members/new");
  await page.getByLabel("Full name").fill("Sita Rai");
  await page.getByLabel("Mobile number").fill(phone);
  await page.getByLabel("Agrees to messages on WhatsApp").check();
  await page.getByLabel("Plan").selectOption({ label: "1 month — Rs 1,500" });
  await page.getByRole("button", { name: "Save member" }).click();
  await page.getByRole("link", { name: "Print receipt" }).click();
  await page.getByRole("button", { name: "Send on WhatsApp" }).click();
  await expect(page.getByText("Sending the receipt on WhatsApp.")).toBeVisible();

  // Sent messages: both by WhatsApp, sent by the worker.
  await page.goto("/staff/sms");
  const welcome = page.getByRole("listitem").filter({ hasText: /Welcome to/ });
  await expect(welcome.getByLabel("WhatsApp")).toBeVisible();
  await expect(welcome.getByText("Sent")).toBeVisible({ timeout: 30_000 });
  const receipt = page.getByRole("listitem").filter({ hasText: /receipt #/ });
  await expect(receipt.getByLabel("WhatsApp")).toBeVisible();

  // The member's own switch, on as the desk ticked it.
  const app = await memberSignsIn(browser, gym.slug, phone);
  await app.getByRole("link", { name: "Me", exact: true }).click();
  const own = app.getByLabel("Messages from the gym on WhatsApp");
  await expect(own).toBeChecked();
  // It follows the server: it flips once the change is saved.
  await own.click();
  await expect(own).not.toBeChecked();
});
