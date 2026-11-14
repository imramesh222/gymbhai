import { createHmac } from "node:crypto";

import { expect, type Browser, type Page, type TestInfo } from "@playwright/test";

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

/**
 * Sign up a gym through the real form, say how it counts plan months on
 * Plans (asked before the first sale, PLAN.md §5.1) and land on the staff
 * dashboard.
 */
export async function signUpGym(
  page: Page,
  planMonths: "AD" | "BS" = "BS",
  path = "/signup",
) {
  const gym = unique();
  await page.goto(path);
  await page.getByLabel("Gym name").fill(gym.gymName);
  await page.getByLabel("Your gym's address").fill(gym.slug);
  await page.getByLabel("Your name").fill("Sita Sharma");
  await page.getByLabel("Mobile number").fill(gym.phone);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("checkbox", { name: /I accept the/ }).check();
  await page.getByRole("button", { name: "Create my gym" }).click();
  await page.waitForURL("**/staff");

  await page.goto("/staff/settings/plans");
  await page.getByText(`${planMonths} months`, { exact: true }).click();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("How do you count months?")).toBeHidden();
  await page.goto("/staff");
  return gym;
}

export const OTP = process.env.OTP_TEST_CODE ?? "246810";

/** Give the seeded 1-month plan a price, from Settings. */
export async function priceOneMonthPlan(page: Page, rupees: string) {
  await page.goto("/staff/settings/plans");
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

/** A code from an authenticator app (RFC 6238), `steps` 30-second steps ahead. */
export function totp(base32Secret: string, steps = 0): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const char of base32Secret.replace(/[\s=]/g, "").toUpperCase()) {
    bits += alphabet.indexOf(char).toString(2).padStart(5, "0");
  }
  const key = Buffer.from((bits.match(/.{8}/g) ?? []).map((byte) => parseInt(byte, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30_000) + steps));
  const digest = createHmac("sha1", key).update(counter).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  const value = digest.readUInt32BE(offset) & 0x7fffffff;
  return String(value % 1_000_000).padStart(6, "0");
}

export const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "e2e-admin@gymbhai.com";
export const ADMIN_PASSWORD =
  process.env.E2E_ADMIN_PASSWORD ?? "e2e-admin-password-123";

/**
 * Sign in as the e2e platform admin. Global setup turned on its two-step
 * sign-in and kept the recovery codes; each test takes its own, since every
 * code from the app works only once (PLAN.md §16.1).
 */
export async function signInAsAdmin(page: Page, testInfo: TestInfo) {
  const codes = JSON.parse(process.env.E2E_ADMIN_RECOVERY_CODES ?? "[]") as string[];
  const index = testInfo.project.name === "phone" ? 1 : 0;
  const code = codes[index * 3 + testInfo.retry];
  if (!code) throw new Error("No recovery code for the e2e admin: see global-setup.ts");
  await page.goto("/staff/login");
  await page.getByLabel("Email or mobile number").fill(ADMIN_EMAIL);
  await page.getByLabel("Password", { exact: true }).fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("button", { name: /Use a recovery code/ }).click();
  await page.getByLabel("Recovery code").fill(code);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/admin");
}

/**
 * Open a screen from the menu: the sidebar on a laptop; on a phone, the tab
 * bar if it is there, otherwise More.
 */
export async function openFromMenu(page: Page, name: string) {
  const link = page
    .getByRole("navigation", { name: "Menu" })
    .getByRole("link", { name, exact: true })
    .filter({ visible: true });
  const more = page
    .getByRole("navigation", { name: "Menu" })
    .getByRole("button", { name: "More" })
    .filter({ visible: true });
  await link.or(more).first().waitFor();
  if (await link.count()) return link.first().click();
  await more.click();
  await page
    .getByRole("dialog", { name: "More" })
    .getByRole("link", { name, exact: true })
    .click();
}

/** Open the whole menu, so a test can check what is in it. */
export async function wholeMenu(page: Page) {
  const more = page
    .getByRole("navigation", { name: "Menu" })
    .getByRole("button", { name: "More" })
    .filter({ visible: true });
  const sidebar = page
    .getByRole("navigation", { name: "Menu" })
    .filter({ visible: true });
  await more.or(sidebar).first().waitFor();
  if (await more.isVisible()) {
    await more.click();
    return page.getByRole("dialog", { name: "More" });
  }
  return sidebar.first();
}

/** Sign out from the menu: the sidebar on a laptop, More on a phone. */
export async function signOut(page: Page) {
  const button = page
    .getByRole("button", { name: "Sign out" })
    .filter({ visible: true });
  const more = page
    .getByRole("navigation", { name: "Menu" })
    .getByRole("button", { name: "More" })
    .filter({ visible: true });
  // Whichever the layout shows, once the page has drawn it.
  await button.or(more).first().waitFor();
  if (await more.isVisible()) await more.click();
  await button.click();
  await page.waitForURL("**/staff/login");
}

/** A member signs in to their gym's app on a phone of their own. */
export async function memberSignsIn(browser: Browser, slug: string, phone: string) {
  const context = await browser.newContext();
  // Headless Chromium always says notifications are "denied"; a phone that
  // was never asked says "default".
  await context.addInitScript(() =>
    Object.defineProperty(Notification, "permission", { get: () => "default" }),
  );
  const app = await context.newPage();
  await app.goto(`/${slug}`);
  await app.getByLabel("Mobile number or email").fill(phone);
  await app.getByRole("button", { name: "Send me a code" }).click();
  await app.getByLabel("Code").fill(OTP);
  await app.getByRole("button", { name: "Sign in" }).click();
  await expect(app.getByText("Show this at the door")).toBeVisible();
  return app;
}

/** Add a member at the desk, with the 1-month plan sold and paid unless not. */
export async function addMember(
  page: Page,
  name: string,
  { plan = "1 month — Rs 1,500", sell = true }: { plan?: string; sell?: boolean } = {},
) {
  const phone = `98${randomDigits(8)}`;
  await page.goto("/staff/members/new");
  await page.getByLabel("Full name").fill(name);
  await page.getByLabel("Mobile number").fill(phone);
  if (sell) await page.getByLabel("Plan").selectOption({ label: plan });
  else await page.getByLabel("Sell a membership now").uncheck();
  await page.getByRole("button", { name: "Save member" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(name) })).toBeVisible();
  return { phone, url: page.url().split("?")[0] };
}
