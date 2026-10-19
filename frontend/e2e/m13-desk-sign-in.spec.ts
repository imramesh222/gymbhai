import { expect, test } from "./fixtures";
import { randomDigits, signUpGym } from "./helpers";

/** PLAN.md §18.4: no SMS code, the member scans the QR the desk shows. */
test("a member signs in on their phone with the desk's QR", async ({
  page,
  browser,
}) => {
  await signUpGym(page);
  await page.goto("/staff/members/new");
  await page.getByLabel("Full name").fill("Sunita Magar");
  await page.getByLabel("Mobile number").fill(`98${randomDigits(8)}`);
  await page.getByLabel("Sell a membership now").uncheck();
  await page.getByRole("button", { name: "Save member" }).click();
  await expect(page.getByRole("heading", { name: /Sunita Magar/ })).toBeVisible();

  await page.getByRole("main").getByRole("button", { name: "More" }).click();
  await page.getByRole("menuitem", { name: "Sign in on their phone" }).click();
  const qr = page.getByRole("img", { name: "Sign-in QR for Sunita Magar" });
  await expect(qr).toBeVisible();
  const link = new URL((await qr.getAttribute("data-qr-value"))!);
  expect(link.hash).toMatch(/^#desk=/);

  // Their phone's camera opens the link: signed in, and the token gone from
  // the address.
  const phone = await (await browser.newContext()).newPage();
  await phone.goto(link.pathname + link.hash);
  await expect(phone.getByText("Show this at the door")).toBeVisible();
  expect(phone.url()).not.toContain("desk=");

  // The desk sees it happen.
  await expect(
    page.getByText("Sunita Magar is signed in on their phone."),
  ).toBeVisible();

  // It worked once: a second phone gets nothing from it.
  const other = await (await browser.newContext()).newPage();
  await other.goto(link.pathname + link.hash);
  await expect(
    other.getByText("This QR has expired or been used. Ask the desk for a new one."),
  ).toBeVisible();
  await expect(other.getByLabel("Mobile number or email")).toBeVisible();
});
