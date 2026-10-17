import { type Page } from "@playwright/test";

import { expect, test } from "./fixtures";
import { randomDigits, signUpGym, wholeMenu } from "./helpers";

async function priceOneMonthPlan(page: Page, rupees: string) {
  await page.goto("/staff/settings/plans");
  await page.getByRole("button", { name: /^1 month/ }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Price").fill(rupees);
  await dialog.getByLabel("Admission fee").fill("500");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: /^1 month.*Rs 1,500/ })).toBeVisible();
}

test("the desk: add a member, part-pay, collect the rest, renew early", async ({
  page,
}) => {
  await signUpGym(page, "AD");
  await priceOneMonthPlan(page, "1500");

  // Add a member and sell the first membership in one save.
  await page.goto("/staff/members/new");
  await page.getByLabel("Full name").fill("Sita Rai");
  const memberPhone = `98${randomDigits(8)}`;
  await page.getByLabel("Mobile number").fill(memberPhone);
  await page.getByLabel("Plan").selectOption({ label: "1 month — Rs 1,500" });
  // The admission fee applies on a first membership: 1,500 + 500.
  await expect(page.getByText("Rs 2,000", { exact: true }).first()).toBeVisible();
  await page.getByLabel("Amount").fill("1200");
  await expect(
    page.getByText("Rs 800 will show as dues to collect later."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Save member" }).click();

  // Profile: active, owing 800, with a receipt to print.
  await expect(page.getByRole("heading", { name: /Sita Rai/ })).toBeVisible();
  await expect(page.getByText("Active").first()).toBeVisible();
  await expect(page.getByText("Rs 800").first()).toBeVisible();
  await page.getByRole("link", { name: "Print receipt" }).click();
  await expect(page.getByText("Payment receipt", { exact: true })).toBeVisible();
  await expect(
    page.getByText("This is a payment receipt, not a VAT invoice."),
  ).toBeVisible();
  await expect(page.getByText("Rs 1,200")).toBeVisible();
  // As a PDF to keep or share (§16.3, 8.4).
  const pdf = page.getByRole("button", { name: "PDF" });
  await expect(pdf).toBeEnabled();
  const [file] = await Promise.all([page.waitForEvent("download"), pdf.click()]);
  expect(file.suggestedFilename()).toMatch(/^receipt-\d+\.pdf$/);
  await page.getByRole("button", { name: "Back" }).click();

  // Collect the rest.
  await page.getByRole("button", { name: "Collect payment" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Amount")).toHaveValue("800");
  await dialog.getByLabel("Paid by").selectOption("esewa");
  await dialog.getByLabel("Transaction ID").fill(`ES-${Date.now()}`);
  await dialog.getByRole("button", { name: "Record payment" }).click();
  await expect(page.getByText(/Payment recorded\. Receipt #2\./)).toBeVisible();
  await expect(page.getByRole("button", { name: "Collect payment" })).toHaveCount(0);

  // Renew early: it queues after the current membership, no admission fee.
  await page.getByRole("link", { name: "Renew" }).click();
  await expect(page.getByText(/The renewal starts on/)).toBeVisible();
  await page.getByLabel("Plan").selectOption({ label: "1 month — Rs 1,500" });
  await expect(page.getByLabel("Admission fee")).toHaveValue("0");
  await page.getByRole("button", { name: "Save renewal" }).click();
  await page.getByRole("tab", { name: /Memberships/ }).click();
  await expect(page.getByText("Starts soon")).toBeVisible();

  // The till: 1,200 + 800 + 1,500 today.
  await page.goto("/staff/payments");
  await expect(page.getByText("Rs 3,500").first()).toBeVisible();

  // And the member list finds her by phone.
  await page.goto("/staff/members");
  await page.getByLabel(/Search by name/).fill(memberPhone.slice(-7));
  await expect(page.getByRole("link", { name: /Sita Rai/ })).toBeVisible();
});

test("the owner adds front-desk staff who cannot see settings", async ({
  page,
  browser,
}) => {
  await signUpGym(page);
  await page.goto("/staff/team");
  await page.getByRole("button", { name: "Add staff" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name").fill("Hari Desk");
  const phone = `98${randomDigits(8)}`;
  await dialog.getByLabel("Mobile number").fill(phone);
  await dialog.getByLabel("Password", { exact: true }).fill("front-desk-123");
  await dialog.getByRole("button", { name: "Front desk" }).click();
  await expect(dialog.getByLabel("Collect payments")).toBeChecked();
  await expect(dialog.getByLabel("Void payments")).not.toBeChecked();
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Hari Desk")).toBeVisible();

  const desk = await (await browser.newContext()).newPage();
  await desk.goto("/staff/login");
  await desk.getByLabel("Email or mobile number").fill(phone);
  await desk.getByLabel("Password", { exact: true }).fill("front-desk-123");
  await desk.getByRole("button", { name: "Sign in" }).click();
  await desk.waitForURL("**/staff");
  const menu = await wholeMenu(desk);
  await expect(menu.getByRole("link", { name: "Members" })).toBeVisible();
  await expect(menu.getByRole("link", { name: "Settings" })).toHaveCount(0);
  await expect(menu.getByRole("link", { name: "Payments" })).toHaveCount(0);
});

test("Save tapped again after a lost answer adds the member and the payment once", async ({
  page,
}) => {
  await signUpGym(page, "AD");
  await priceOneMonthPlan(page, "1500");

  // The first save reaches the server, but its answer never reaches the
  // page: weak mobile data at the desk.
  let dropped = false;
  await page.route("**/api/v1/members", async (route) => {
    if (route.request().method() !== "POST" || dropped) return route.continue();
    dropped = true;
    await route.fetch();
    await route.abort("connectionreset");
  });

  await page.goto("/staff/members/new");
  await page.getByLabel("Full name").fill("Hari Thapa");
  await page.getByLabel("Mobile number").fill(`98${randomDigits(8)}`);
  await page.getByLabel("Plan").selectOption({ label: "1 month — Rs 1,500" });
  await page.getByRole("button", { name: "Save member" }).click();
  await expect(page.getByText(/Can.t reach GymBhai/)).toBeVisible();

  // The same form, tapped again: the first answer comes back.
  await page.getByRole("button", { name: "Save member" }).click();
  await expect(page.getByRole("heading", { name: /Hari Thapa/ })).toBeVisible();

  await page.goto("/staff/members");
  await expect(page.getByText("Hari Thapa").filter({ visible: true })).toHaveCount(1);
  await page.goto("/staff/payments");
  await expect(page.getByText("Hari Thapa").filter({ visible: true })).toHaveCount(1);
});

test("the owner erases a member who asks, and the accounts stay", async ({ page }) => {
  await signUpGym(page, "AD");
  await priceOneMonthPlan(page, "1500");
  await page.goto("/staff/members/new");
  await page.getByLabel("Full name").fill("Gita Gurung");
  await page.getByLabel("Mobile number").fill(`98${randomDigits(8)}`);
  await page.getByLabel("Plan").selectOption({ label: "1 month — Rs 1,500" });
  await page.getByRole("button", { name: "Save member" }).click();
  await expect(page.getByRole("heading", { name: /Gita Gurung/ })).toBeVisible();

  await page.getByRole("main").getByRole("button", { name: "More" }).click();
  await page.getByRole("menuitem", { name: "Erase member…" }).click();
  const dialog = page.getByRole("dialog");
  const erase = dialog.getByRole("button", { name: "Erase for good" });
  await expect(erase).toBeDisabled();
  await dialog.getByLabel(/Type .Gita Gurung. to confirm/).fill("gita gurung");
  await erase.click();

  await expect(page.getByRole("heading", { name: /Erased member/ })).toBeVisible();
  await expect(page.getByText(/This member's details were erased on/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit" })).toHaveCount(0);
  // The sale and its payment are still the gym's.
  await expect(page.getByText("1 month").first()).toBeVisible();
  await page.goto("/staff/payments");
  await expect(page.getByText("Erased member").first()).toBeVisible();
});

test("extend everyone says how many first, and needs the number typed", async ({
  page,
}) => {
  await signUpGym(page, "AD");
  await priceOneMonthPlan(page, "1500");
  await page.goto("/staff/members/new");
  await page.getByLabel("Full name").fill("Ram Thapa");
  await page.getByLabel("Mobile number").fill(`98${randomDigits(8)}`);
  await page.getByLabel("Plan").selectOption({ label: "1 month — Rs 1,500" });
  await page.getByRole("button", { name: "Save member" }).click();
  await expect(page.getByRole("heading", { name: /Ram Thapa/ })).toBeVisible();

  await page.goto("/staff/members");
  await page.getByRole("main").getByRole("button", { name: "More" }).click();
  await page.getByRole("menuitem", { name: "Extend everyone" }).click();
  const form = page.getByRole("dialog", { name: "Extend everyone" });
  await form.getByLabel("Days").fill("7");
  await form.getByLabel("Reason").fill("Closed for Dashain");
  await form.getByRole("button", { name: "Continue" }).click();

  const confirm = page.getByRole("dialog", { name: "Extend everyone" }).last();
  await expect(
    confirm.getByText(/Adds 7 days to the 1 current membership/),
  ).toBeVisible();
  const go = confirm.getByRole("button", { name: "Extend memberships" });
  await expect(go).toBeDisabled();
  await confirm.getByLabel("Type “1” to confirm").fill("1");
  await go.click();
  await expect(page.getByText("1 membership extended.")).toBeVisible();
});
