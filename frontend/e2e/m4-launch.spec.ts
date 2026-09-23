import { expect, test } from "@playwright/test";

import { priceOneMonthPlan, randomDigits, signUpGym } from "./helpers";

const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "e2e-admin@gymbhai.com";
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "e2e-admin-password-123";

test("Today, the monthly report, import and export", async ({ page }) => {
  await signUpGym(page);
  await priceOneMonthPlan(page, "1500");

  // A sale shows up on Today and in the month's report.
  await page.goto("/staff/members/new");
  await page.getByLabel("Full name").fill("Sita Rai");
  await page.getByLabel("Mobile number").fill(`98${randomDigits(8)}`);
  await page.getByLabel("Plan").selectOption({ label: "1 month — Rs 1,500" });
  await page.getByRole("button", { name: "Save member" }).click();
  await expect(page.getByRole("link", { name: "Print receipt" })).toBeVisible();

  await page.goto("/staff");
  await expect(page.getByText("Collected today").first()).toBeVisible();
  await expect(page.getByText("Rs 1,500").first()).toBeVisible();

  await page.getByRole("link", { name: "Reports" }).click();
  await page.waitForURL("**/staff/reports");
  // The gym shows BS dates, so this is a BS month.
  await expect(
    page
      .getByText(
        /Baisakh|Jestha|Asar|Shrawan|Bhadra|Asoj|Kartik|Mangsir|Poush|Magh|Falgun|Chaitra/,
      )
      .first(),
  ).toBeVisible();
  await expect(page.getByText("New members")).toBeVisible();

  // Import a register with a BS expiry date.
  await page.goto("/staff/data");
  const register = [
    "Name,Mobile,Package,Expiry",
    `Hari Thapa,98${randomDigits(8)},3 months,2083-09-15`,
    "No Phone,,1 month,2083-09-15",
  ].join("\n");
  await page.getByLabel("Choose a register file").setInputFiles({
    name: "register.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(register),
  });
  await expect(page.getByText("2 rows, 1 ready to import.")).toBeVisible();
  await expect(page.getByText("Row 2: no phone number")).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Import 1 members" }).click();
  await expect(page.getByText("1 members imported, 0 already here.")).toBeVisible();

  // Export: a real Excel file.
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Members", exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(
    /-members-\d{4}-\d{2}-\d{2}\.xlsx$/,
  );
});

test("the owner pays us, and the admin activates it", async ({ page, browser }) => {
  // Our price list first, from /admin.
  const admin = await (await browser.newContext()).newPage();
  await admin.goto("/staff/login");
  await admin.getByLabel("Email or mobile number").fill(ADMIN_EMAIL);
  await admin.getByLabel("Password", { exact: true }).fill(ADMIN_PASSWORD);
  await admin.getByRole("button", { name: "Sign in" }).click();
  await admin.waitForURL("**/admin");
  await admin.getByRole("link", { name: "Our plans and prices" }).click();
  const planName = `Standard ${randomDigits(4)}`;
  const newPlan = admin.locator("section", { hasText: "New plan" });
  await newPlan.getByLabel("Plan name").fill(planName);
  await newPlan.getByLabel("Price per month").fill("2000");
  await newPlan.getByRole("button", { name: "Add" }).click();
  await expect(admin.getByRole("heading", { name: planName })).toBeVisible();

  // The owner tells us they've paid.
  const gym = await signUpGym(page);
  await page.goto("/staff/subscription");
  await page.getByLabel("Plan").selectOption({ label: `${planName} — 2,000/month` });
  await page.getByLabel("Months").fill("3");
  await expect(page.getByLabel("Amount paid")).toHaveValue("6000");
  const ref = `ES-${randomDigits(8)}`;
  await page.getByLabel("Transaction ID").fill(ref);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(
    page.getByText("Sent. We'll confirm by SMS once we've checked it."),
  ).toBeVisible();

  // We check and approve.
  await admin.getByRole("link", { name: "Gyms" }).click();
  const pending = admin.locator("li", { hasText: ref });
  await expect(pending).toContainText(gym.gymName);
  await pending.getByRole("button", { name: "Approve" }).click();
  await expect(
    admin.getByText("Approved. The gym has been told by SMS."),
  ).toBeVisible();

  await page.reload();
  await expect(page.getByText(planName).first()).toBeVisible();
  await expect(page.getByText("confirmed")).toBeVisible();
});
