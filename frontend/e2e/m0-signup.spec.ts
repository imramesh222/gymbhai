import { expect, test } from "./fixtures";
import { OTP, PASSWORD, signOut, signUpGym, totp } from "./helpers";

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

  await signOut(page);

  await page.getByLabel("Email or mobile number").fill(`+977 ${gym.phone}`);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/staff");
  await expect(page.getByText(gym.gymName).filter({ visible: true })).toBeVisible();
});

test("the dashboard sends signed-out visitors to sign in", async ({ page }) => {
  await page.goto("/staff");
  await page.waitForURL("**/staff/login");
});

test("an owner who forgot their password sets a new one with a code", async ({
  page,
}) => {
  const gym = await signUpGym(page);
  await signOut(page);

  await page.getByRole("link", { name: "Forgot your password?" }).click();
  // The sign-in form has a field with the same label: wait until it's gone.
  await page.waitForURL("**/staff/forgot");
  await page.getByLabel("Email or mobile number").fill(gym.phone);
  await page.getByRole("button", { name: "Send me a code" }).click();
  await page.getByLabel("Code").fill(OTP);
  await page.getByLabel("New password").fill("a-brand-new-password");
  await page.getByRole("button", { name: "Set new password" }).click();
  await expect(page.getByText("Your password has been changed.")).toBeVisible();

  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/staff/login");
  await page.getByLabel("Email or mobile number").fill(gym.phone);
  await page.getByLabel("Password", { exact: true }).fill("a-brand-new-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/staff");
});

test("an owner turns on two-step sign-in and signs in with the app's code", async ({
  page,
}) => {
  const gym = await signUpGym(page);
  await page.goto("/staff/profile");
  await page.getByRole("button", { name: "Set up two-step sign-in" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Your password").fill(PASSWORD);
  await dialog.getByRole("button", { name: "Continue" }).click();
  const secret = (await dialog.getByTestId("two-step-secret").textContent()) ?? "";
  await dialog.getByLabel("6-digit code").fill(totp(secret));
  await dialog.getByRole("button", { name: "Turn on" }).click();
  await expect(dialog.getByRole("list", { name: "Recovery codes" })).toBeVisible();
  await dialog.getByRole("button", { name: "I've saved them" }).click();
  await expect(page.getByText("10 recovery codes left.")).toBeVisible();

  await signOut(page);
  await page.getByLabel("Email or mobile number").fill(gym.phone);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  // The setup code's 30 seconds are used up: the next step's code is accepted.
  await page.getByLabel("6-digit code").fill(totp(secret, 1));
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/staff");
});

test("signing out another device from My account sends it to sign-in at once", async ({
  page,
  browser,
}) => {
  const gym = await signUpGym(page);
  await expect(page.getByRole("heading", { name: "Welcome, Sita" })).toBeVisible();

  // The same owner on a second device.
  const other = await (await browser.newContext()).newPage();
  await other.goto("/staff/login");
  await other.getByLabel("Email or mobile number").fill(gym.phone);
  await other.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await other.getByRole("button", { name: "Sign in" }).click();
  await other.waitForURL("**/staff");
  await other.goto("/staff/profile");
  const devices = other.locator("section", { hasText: "Signed-in devices" });
  await expect(devices.getByText("This device")).toBeVisible();
  await devices.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(devices.getByText("That device has been signed out.")).toBeVisible();

  // The first device hears about it live and is signed out, untouched.
  await page.waitForURL("**/staff/login");
});
