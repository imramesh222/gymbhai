import { expect, test } from "./fixtures";
import { openFromMenu, randomDigits, signUpGym } from "./helpers";

test("follow up, a reminder by SMS, and a notice with its cost shown first", async ({
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

  await openFromMenu(page, "Follow up");
  await page.waitForURL("**/staff/follow-up");
  const week = page.locator("section", { hasText: "Ends this week" });
  await expect(week.getByText("Ram Thapa")).toBeVisible();
  await week.getByRole("button", { name: "Send message" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Send reminder" }).click();
  await expect(page.getByText("Message sent to Ram Thapa.")).toBeVisible();
  // Joined today, so not "not visiting" yet: that tab names the rule instead.
  await page.getByRole("tab", { name: /Not visiting/ }).click();
  await expect(page).toHaveURL(/tab=not-visiting/);
  await expect(
    page.getByText("Active members with no visit in 14 days."),
  ).toBeVisible();
  await expect(page.getByText("Ram Thapa")).toHaveCount(0);

  // The SMS log shows the welcome and the reminder; the worker sends them.
  await openFromMenu(page, "SMS");
  await page.waitForURL("**/staff/sms");
  await expect(page.getByRole("heading", { name: "Sent messages" })).toBeVisible();
  await expect(page.getByText("· reminder")).toBeVisible();
  await expect(page.getByText("· welcome")).toBeVisible();
  await expect(async () => {
    await page.reload();
    await expect(page.getByText("Sent", { exact: true }).first()).toBeVisible();
  }).toPass({ timeout: 20_000 });

  // A notice to their phones: the cost comes first. Nobody has notifications
  // on yet, so it is all SMS.
  await openFromMenu(page, "Notices");
  await page.waitForURL("**/staff/notices");
  await page.getByLabel("Title").fill("Closed on Saturday");
  await page.getByLabel("Message").fill("The gym is closed for Tihar.");
  await page.getByLabel("Also send SMS to members without notifications").check();
  await page.getByRole("button", { name: "Check the cost" }).click();
  await expect(
    page.getByText(/1 members: 0 by notification, 1 by SMS \(1 credits\)/),
  ).toBeVisible();
  await page.getByRole("button", { name: "Publish and send" }).click();
  await expect(page.getByText("Published, and on its way to 1 members.")).toBeVisible();
});

test("automations: turn one on, and the wording shows its SMS cost", async ({
  page,
}) => {
  await signUpGym(page);
  // The old address still lands here.
  await page.goto("/staff/settings/reminders");
  await page.waitForURL("**/staff/automations");

  // Win-back comes switched off; turning it on is one tick.
  const winBack = page.locator("section", { hasText: "Win back" });
  const rule = winBack.getByRole("checkbox", { name: /30 days after it ended/ });
  await expect(rule).not.toBeChecked();
  await rule.check();
  await expect(page.getByText("Turned on.")).toBeVisible();
  await page.reload();
  await expect(rule).toBeChecked();

  const birthday = page.locator("section", { hasText: "Birthday" });
  await birthday.getByLabel("Wording").fill("नमस्ते {name}, जन्मदिनको शुभकामना!");
  await expect(
    birthday.getByText(/Nepali text fits 70 characters per SMS/),
  ).toBeVisible();
  await birthday.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved.", { exact: true })).toBeVisible();
});
