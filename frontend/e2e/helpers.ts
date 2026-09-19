import { expect, type Page } from "@playwright/test";

/** Unique per run, so tests never collide on slugs or phone numbers. */
export function randomDigits(count: number): string {
  return Array.from({ length: count }, () => Math.floor(Math.random() * 10)).join("");
}

export function unique() {
  const n = randomDigits(8);
  return {
    slug: `e2e-${n}`,
    phone: `98${n}`,
    gymName: `E2E Gym ${n}`,
  };
}

export const PASSWORD = "correct-horse-battery";

/** Sign up a gym through the real form and land on the staff dashboard. */
export async function signUpGym(page: Page, planMonths: "AD" | "BS" = "BS") {
  const gym = unique();
  await page.goto("/signup");
  await page.getByLabel("Gym name").fill(gym.gymName);
  await page.getByLabel("Your gym's address").fill(gym.slug);
  await page.getByText(`${planMonths} months`, { exact: true }).click();
  await page.getByText("Both", { exact: true }).click();
  await page.getByLabel("Your name").fill("Sita Sharma");
  await page.getByLabel("Mobile number").fill(gym.phone);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create my gym" }).click();
  await page.waitForURL("**/staff");
  return gym;
}

export const OTP = process.env.OTP_TEST_CODE ?? "246810";

/** Give the seeded 1-month plan a price, from Settings. */
export async function priceOneMonthPlan(page: Page, rupees: string) {
  await page.goto("/staff/settings");
  await page.getByRole("button", { name: /^1 month/ }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Price").fill(rupees);
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(
    page.getByRole("button", {
      name: new RegExp(
        `^1 month.*Rs ${new Intl.NumberFormat("en-IN").format(Number(rupees))}`,
      ),
    }),
  ).toBeVisible();
}
