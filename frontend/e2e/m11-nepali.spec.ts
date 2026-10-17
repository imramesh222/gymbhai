import { expect, test } from "./fixtures";
import { signUpGym } from "./helpers";

/** PLAN.md §16.6: Nepali, chosen before signing in and for each account. */
test("नेपाली: the sign-in screen, then a staff account's own language", async ({
  page,
}) => {
  await page.goto("/staff/login");
  await page.getByRole("button", { name: "नेपाली" }).click();
  await expect(page.getByRole("heading", { name: "कर्मचारी साइन इन" })).toBeVisible();
  // Remembered: the next visit opens in Nepali.
  await page.reload();
  await expect(page.getByRole("heading", { name: "कर्मचारी साइन इन" })).toBeVisible();
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByRole("heading", { name: "Staff sign in" })).toBeVisible();

  // An English gym; this owner chooses Nepali for themselves.
  await signUpGym(page);
  await page.goto("/staff/profile");
  await page.getByLabel("Show GymBhai in").selectOption({ label: "नेपाली" });
  await expect(page.getByRole("link", { name: "आज" }).first()).toBeAttached();
  await expect(page.getByText("दुई-चरण साइन इन").first()).toBeVisible();

  // Back to the gym's language.
  await page
    .getByLabel("GymBhai यस भाषामा देखाउनुहोस्")
    .selectOption({ label: "जिमको भाषा (English)" });
  await expect(page.getByText("Two-step sign-in").first()).toBeVisible();
});
