import { expect, test } from "@playwright/test";

import { PASSWORD, signUpGym } from "./helpers";

test("sign up a gym, sign out, sign back in with the phone number", async ({
  page,
}) => {
  const gym = await signUpGym(page);

  await expect(page.getByRole("heading", { name: "Welcome, Sita" })).toBeVisible();
  await expect(page.getByText("14 days left in your free trial.")).toBeVisible();
  await expect(page.getByText(`app.gymbhai.com/${gym.slug}`)).toBeVisible();

  // A reload keeps the session: the refresh cookie restores it.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Welcome, Sita" })).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await page.waitForURL("**/staff/login");

  await page.getByLabel("Email or mobile number").fill(`+977 ${gym.phone}`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/staff");
  await expect(page.getByText(gym.gymName)).toBeVisible();
});

test("the dashboard sends signed-out visitors to sign in", async ({ page }) => {
  await page.goto("/staff");
  await page.waitForURL("**/staff/login");
});
