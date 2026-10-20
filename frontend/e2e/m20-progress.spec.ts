import { expect, test } from "./fixtures";
import { addMember, memberSignsIn, priceOneMonthPlan, signUpGym } from "./helpers";

/**
 * PLAN.md §19.5: a check recorded at the desk and one in the member's app,
 * each seeing both, with the change between them.
 */
test("progress: a check at the desk, one in the app", async ({ page, browser }) => {
  const gym = await signUpGym(page, "AD");
  await priceOneMonthPlan(page, "1500");
  const member = await addMember(page, "Sita Rai");

  await page.getByRole("tab", { name: "Progress" }).click();
  await page.getByRole("button", { name: "Record a check" }).click();
  const check = page.getByRole("dialog", { name: "Record a check" });
  await check.getByLabel("Weight (kg)").fill("72.5");
  await check.getByLabel("Waist (cm)").fill("84");
  await check.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("72.5 kg").first()).toBeVisible();

  const app = await memberSignsIn(browser, gym.slug, member.phone);
  await app.getByRole("link", { name: /Your progress/ }).click();
  await expect(app.getByText("72.5 kg").first()).toBeVisible();
  await app.getByRole("button", { name: "Record a check" }).click();
  const own = app.getByRole("dialog", { name: "Record a check" });
  await own.getByLabel("Weight (kg)").fill("71");
  await own.getByRole("button", { name: "Save" }).click();
  await expect(app.getByText("71 kg").first()).toBeVisible();
  await expect(app.getByText(/−1\.5 kg since the last/)).toBeVisible();

  // The desk sees the member's own check too, and can't change it.
  await page.reload();
  await expect(page.getByText("71 kg").first()).toBeVisible();
  await expect(page.getByText("Recorded by the member in their app")).toBeVisible();
});
