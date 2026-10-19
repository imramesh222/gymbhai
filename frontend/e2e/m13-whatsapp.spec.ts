import { expect, test } from "./fixtures";
import { priceOneMonthPlan, randomDigits, signUpGym } from "./helpers";

/** PLAN.md §18.5: the gym's own wording, sent from the desk's own WhatsApp. */
test("WhatsApp: the gym's message, filled in for the member", async ({ page }) => {
  await signUpGym(page, "AD");
  await priceOneMonthPlan(page, "1500");
  const phone = `98${randomDigits(8)}`;
  await page.goto("/staff/members/new");
  await page.getByLabel("Full name").fill("Hari Thapa");
  await page.getByLabel("Mobile number").fill(phone);
  await page.getByLabel("Plan").selectOption({ label: "1 month — Rs 1,500" });
  await page.getByRole("button", { name: "Save member" }).click();
  await expect(page.getByRole("heading", { name: /Hari Thapa/ })).toBeVisible();

  await page.getByRole("main").getByRole("button", { name: "More" }).click();
  await page.getByRole("menuitem", { name: "Send on WhatsApp" }).click();
  const dialog = page.getByRole("dialog", { name: "Send on WhatsApp" });
  const message = dialog.getByLabel("Message", { exact: true });
  const open = dialog.getByRole("link", { name: "Open WhatsApp" });

  // Never in the app yet: the welcome, with the app's link.
  await expect(message).toHaveValue(/Hari/);
  await expect(message).toHaveValue(/http/);
  await expect(open).toHaveAttribute(
    "href",
    new RegExp(`^https://wa\\.me/977${phone}\\?text=`),
  );

  // Another message, and the desk's own words on top.
  await dialog
    .getByLabel("What it's about")
    .selectOption({ label: "Renewal reminder" });
  await expect(message).toHaveValue(/^Hi Hari/);
  await message.fill("Namaste Hari, see you tomorrow!");
  await expect(open).toHaveAttribute(
    "href",
    `https://wa.me/977${phone}?text=${encodeURIComponent("Namaste Hari, see you tomorrow!")}`,
  );
});
