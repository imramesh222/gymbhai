import { expect, test } from "./fixtures";
import { randomDigits, signUpGym } from "./helpers";

/**
 * PLAN.md §18.3: a PT plan, sold with a part payment, a session recorded,
 * what's owed in Follow up, the rest collected; Reports, the trainer's list,
 * and the member's Home.
 */
test("personal training: sell a pack, record a session, the member sees it", async ({
  page,
  browser,
}) => {
  await signUpGym(page);

  // Settings → Personal training: a pack of 12 sessions within 2 months.
  await page.goto("/staff/settings/personal-training");
  await page.getByRole("button", { name: "Add PT plan" }).click();
  const planDialog = page.getByRole("dialog", { name: "Add PT plan" });
  await planDialog.getByLabel("Plan name").fill("12 sessions");
  await planDialog.getByLabel("Kind").selectOption({ label: "Pack of sessions" });
  await planDialog.getByLabel("Sessions in the pack").fill("12");
  await planDialog.getByLabel("Length").fill("2");
  await planDialog.getByLabel("Price").fill("12000");
  await planDialog.getByRole("button", { name: "Save" }).click();
  await expect(
    page.getByRole("button", {
      name: /12 sessions · 12 sessions · 2 months.*Rs 12,000/,
    }),
  ).toBeVisible();

  await page.goto("/staff/members/new");
  await page.getByLabel("Full name").fill("Hari Thapa");
  await page.getByLabel("Mobile number").fill(`98${randomDigits(8)}`);
  await page.getByLabel("Sell a membership now").uncheck();
  await page.getByRole("button", { name: "Save member" }).click();
  await expect(page.getByRole("heading", { name: /Hari Thapa/ })).toBeVisible();

  // Sold with Rs 5,000 now; the owner trains too, and is chosen already.
  await page.getByRole("tab", { name: /Personal training/ }).click();
  await page.getByRole("button", { name: "Sell personal training" }).click();
  const sale = page.getByRole("dialog", { name: "Sell personal training" });
  await sale.getByLabel("PT plan").selectOption({ label: "12 sessions — Rs 12,000" });
  await expect(sale.getByLabel("Trainer")).toHaveValue(/.+/);
  await sale.getByLabel("Amount").fill("5000");
  await sale.getByRole("button", { name: "Sell personal training" }).click();
  await expect(page.getByText("Personal training sold.")).toBeVisible();

  const pack = page.getByRole("region", { name: "12 sessions" });
  await expect(pack.getByText("12 of 12 sessions left")).toBeVisible();
  await expect(pack.getByText("Owes")).toBeVisible();
  // Its own money: the profile's header, which collects membership dues,
  // offers nothing; only the package's card does.
  await expect(
    page.getByRole("main").getByRole("button", { name: "Collect payment" }),
  ).toHaveCount(1);

  await pack.getByRole("button", { name: "Record session" }).click();
  const session = page.getByRole("dialog", { name: "Record a session" });
  await session.getByLabel("Note").fill("Legs and core");
  await session.getByRole("button", { name: "Record session" }).click();
  await expect(page.getByText("Session recorded.")).toBeVisible();
  await expect(pack.getByText("11 of 12 sessions left")).toBeVisible();

  // Follow up → Owe money: what's owed on personal training, in its own
  // list; the row opens the member's Personal training tab.
  await page.goto("/staff/follow-up?tab=owing");
  const owed = page.getByRole("listitem").filter({ hasText: "Hari Thapa" });
  await expect(owed.getByText(/12 sessions with Sita Sharma/)).toBeVisible();
  await expect(owed.getByText("Rs 7,000")).toBeVisible();
  await owed.getByRole("link", { name: /Hari Thapa/ }).click();

  await pack.getByRole("button", { name: "Collect payment" }).click();
  const collect = page.getByRole("dialog", { name: "Collect payment" });
  await expect(collect.getByLabel("Amount")).toHaveValue("7000");
  await collect.getByRole("button", { name: "Record payment" }).click();
  await expect(page.getByText(/Payment recorded\. Receipt #\d+\./)).toBeVisible();
  await expect(pack.getByText("Owes")).toHaveCount(0);

  // Reports: the month's personal training, and each trainer's.
  await page.goto("/staff/reports");
  const income = page.getByText("From personal training", { exact: true });
  await expect(income.locator("xpath=..")).toContainText("Rs 12,000");
  await expect(page.getByRole("row", { name: "Sita Sharma 1 1" })).toBeVisible();

  // The trainer's own list, with Record session one tap away.
  await page.goto("/staff/pt");
  const client = page.getByRole("listitem").filter({ hasText: "Hari Thapa" });
  await expect(client.getByText(/12 sessions · 11 of 12 sessions left/)).toBeVisible();
  await expect(client.getByRole("button", { name: "Record session" })).toBeVisible();

  // The member's Home shows it, after signing in with the desk's QR.
  await client.getByRole("link", { name: "Hari Thapa" }).click();
  await page
    .getByRole("main")
    .getByRole("button", { name: "More", exact: true })
    .click();
  await page.getByRole("menuitem", { name: "Sign in on their phone" }).click();
  const qr = page.getByRole("img", { name: "Sign-in QR for Hari Thapa" });
  const link = new URL((await qr.getAttribute("data-qr-value"))!);
  const phone = await (await browser.newContext()).newPage();
  await phone.goto(link.pathname + link.hash);
  await expect(phone.getByText("Personal training", { exact: true })).toBeVisible();
  await expect(phone.getByText("With Sita Sharma")).toBeVisible();
  await expect(phone.getByText("11 of 12 sessions left")).toBeVisible();
});
