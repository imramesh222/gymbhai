import { expect, test } from "./fixtures";
import { memberSignsIn, randomDigits, signUpGym } from "./helpers";

/**
 * PLAN.md §19.1: a couple's plan, sold to one with the other added there,
 * the money on the payer's membership, and the other's app saying who pays.
 */
test("a couple's plan: one sale, two memberships, one payer", async ({
  page,
  browser,
}) => {
  const gym = await signUpGym(page, "AD");
  await page.goto("/staff/settings/plans");
  await page.getByRole("button", { name: "Add plan" }).click();
  const plan = page.getByRole("dialog", { name: "Add plan" });
  await plan.getByLabel("Plan name").fill("Couple 1 year");
  await plan.getByLabel("Length").fill("12");
  await plan.getByLabel("Price").fill("30000");
  await plan.getByLabel("People").selectOption("2");
  await plan.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: /^Couple 1 year/ })).toBeVisible();

  const phone = `98${randomDigits(8)}`;
  const partner = `98${randomDigits(8)}`;
  await page.goto("/staff/members/new");
  await page.getByLabel("Full name").fill("Ram Rai");
  await page.getByLabel("Mobile number").fill(phone);
  await page.getByLabel("Plan").selectOption({ label: "Couple 1 year — Rs 30,000" });
  await expect(page.getByText("Who else is on it?")).toBeVisible();
  await page.getByRole("button", { name: "Add someone new" }).click();
  await page.getByLabel("Their name").fill("Gita Rai");
  await page.getByLabel("Their mobile number").fill(partner);
  await page.getByRole("button", { name: "Add them" }).click();
  await expect(page.getByText("Gita Rai")).toBeVisible();
  await page.getByRole("button", { name: "Save member" }).click();
  await expect(page.getByRole("heading", { name: /Ram Rai/ })).toBeVisible();

  // Both on it; the payer's membership carries the money.
  await page.getByRole("tab", { name: /Memberships/ }).click();
  await page.getByRole("link", { name: /Couple 1 year/ }).click();
  await page.waitForURL("**/staff/memberships/**");
  await expect(page.getByText("On this plan")).toBeVisible();
  await expect(page.getByText("Gita Rai")).toBeVisible();

  // Gita's app: her own membership, and who pays for it.
  const app = await memberSignsIn(browser, gym.slug, partner);
  await expect(app.getByText("Ram Rai pays for this")).toBeVisible();
  await expect(app.getByText("days left", { exact: true })).toBeVisible();
});
