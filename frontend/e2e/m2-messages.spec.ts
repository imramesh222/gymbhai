import { expect, test } from "@playwright/test";

import { randomDigits, signUpGym } from "./helpers";

test("expiring list, a reminder by SMS, and a notice with its cost shown first", async ({
  page,
}) => {
  await signUpGym(page, "AD");

  // A member whose month ends in 5 days: sold with a backdated start.
  await page.goto("/staff/members/new");
  await page.getByLabel("Full name").fill("Ram Thapa");
  await page.getByLabel("Mobile number").fill(`98${randomDigits(8)}`);
  await page.getByLabel("Plan").selectOption({ index: 1 });
  await page.getByLabel("Price").fill("1500");
  const end = new Date(Date.now() + 5 * 86_400_000).toISOString().slice(0, 10);
  const start = new Date(Date.now() - 20 * 86_400_000).toISOString().slice(0, 10);
  await page.getByLabel("Starts").fill(start);
  await page.getByLabel("Ends (last day)").fill(end);
  await page.getByRole("button", { name: "Save member" }).click();
  await expect(page.getByRole("heading", { name: /Ram Thapa/ })).toBeVisible();

  await page.getByRole("link", { name: "Expiring" }).click();
  await page.waitForURL("**/staff/expiring");
  const week = page.locator("section", { hasText: "Ends this week" });
  await expect(week.getByText("Ram Thapa")).toBeVisible();
  await week.getByRole("button", { name: "Send reminder" }).click();
  await expect(week.getByRole("button", { name: "Reminder sent" })).toBeDisabled();

  // The SMS log shows the welcome and the reminder; the worker sends them.
  await page.getByRole("link", { name: "SMS" }).click();
  await page.waitForURL("**/staff/sms");
  await expect(page.getByRole("heading", { name: "Sent messages" })).toBeVisible();
  await expect(page.getByText("· reminder")).toBeVisible();
  await expect(page.getByText("· welcome")).toBeVisible();
  await expect(async () => {
    await page.reload();
    await expect(page.getByText("Sent", { exact: true }).first()).toBeVisible();
  }).toPass({ timeout: 20_000 });

  // A notice by SMS: the cost comes first.
  await page.getByRole("link", { name: "Notices" }).click();
  await page.waitForURL("**/staff/notices");
  await page.getByLabel("Title").fill("Closed on Saturday");
  await page.getByLabel("Message").fill("The gym is closed for Tihar.");
  await page.getByLabel("Also send by SMS").check();
  await page.getByRole("button", { name: "Check SMS cost" }).click();
  await expect(page.getByText(/1 members will get this SMS: 1 credits/)).toBeVisible();
  await page.getByRole("button", { name: "Publish and send SMS" }).click();
  await expect(
    page.getByText("Published, and SMS on its way to 1 members."),
  ).toBeVisible();
});

test("reminder wording shows how many SMS it costs", async ({ page }) => {
  await signUpGym(page);
  await page.goto("/staff/settings");
  const add = page.locator("form", { hasText: "Add a reminder" });
  await add
    .getByLabel("Wording")
    .fill("नमस्ते {name}, तपाईंको सदस्यता छिट्टै सकिँदैछ।");
  await expect(add.getByText(/Nepali text fits 70 characters per SMS/)).toBeVisible();
});
