import { expect, test } from "./fixtures";
import { openFromMenu, signUpGym } from "./helpers";

/** PLAN.md §18.1: what the gym spent, and the profit that leaves. */
test("an expense: record it, repeat it, void the repeat, see the profit", async ({
  page,
}) => {
  await signUpGym(page);
  await openFromMenu(page, "Expenses");
  await page.waitForURL("**/staff/expenses");
  await expect(page.getByText("No expenses this month.")).toBeVisible();

  await page.getByRole("button", { name: "Add expense" }).first().click();
  const add = page.getByRole("dialog", { name: "Add expense" });
  await add.getByLabel("Category").selectOption({ label: "Rent" });
  await add.getByLabel("Amount").fill("25000");
  await add.getByLabel("Paid by").selectOption({ label: "Bank transfer" });
  await add.getByLabel(/Paid to/).fill("Hari Shrestha");
  await add.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Expense of Rs 25,000 recorded.")).toBeVisible();
  const rent = page.getByRole("listitem").filter({ hasText: "Rent · Hari Shrestha" });
  await expect(rent).toHaveCount(1);

  // Same again: next month's rent, filled in from this one.
  await rent.getByRole("button", { name: "More" }).click();
  await page.getByRole("menuitem", { name: "Same again" }).click();
  const again = page.getByRole("dialog", { name: "Add expense" });
  await expect(again.getByLabel("Amount")).toHaveValue("25000");
  await again.getByRole("button", { name: "Save" }).click();
  await expect(rent).toHaveCount(2);

  // It was this month's twice by mistake: void one, with a reason.
  await rent.first().getByRole("button", { name: "More" }).click();
  await page.getByRole("menuitem", { name: "Void expense" }).click();
  const voiding = page.getByRole("dialog", { name: "Void expense" });
  await voiding.getByLabel("Reason").fill("Entered twice");
  await voiding.getByRole("button", { name: "Void expense" }).click();
  await expect(page.getByText("Voided: Entered twice")).toBeVisible();
  await expect(page.getByLabel("By category")).toContainText("Rs 25,000");

  // Nothing came in yet, so the month is Rs 25,000 down.
  await openFromMenu(page, "Reports");
  await page.waitForURL("**/staff/reports");
  await expect(page.getByText("−Rs 25,000").first()).toBeVisible();
  await expect(page.getByText("Spent by category")).toBeVisible();
});
