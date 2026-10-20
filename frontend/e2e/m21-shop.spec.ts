import { expect, test } from "./fixtures";
import { randomDigits, signUpGym } from "./helpers";

/**
 * PLAN.md §20.1: products with stock, a walk-in's sale at the till (tapped and
 * scanned), the till refusing what isn't on the shelf, and a void putting the
 * stock back.
 */
test("the shop: a walk-in buys protein and water, and a void puts them back", async ({
  page,
}) => {
  await signUpGym(page, "AD");
  const barcode = `89${randomDigits(10)}`;

  await page.goto("/staff/shop?tab=products");
  for (const [name, rupees, stock, code] of [
    ["Whey protein 2 lb", "6500", "1", ""],
    ["Water 1 litre", "30", "10", barcode],
  ]) {
    await page.getByRole("button", { name: "Add a product" }).first().click();
    const dialog = page.getByRole("dialog", { name: "Add a product" });
    await dialog.getByLabel("Name").fill(name);
    await dialog.getByLabel("Price").fill(rupees);
    if (code) await dialog.getByLabel(/Barcode/).fill(code);
    await dialog.getByLabel("On the shelf now").fill(stock);
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(dialog).toHaveCount(0);
  }

  // The till: protein tapped, water scanned twice, a walk-in paying cash.
  await page.goto("/staff/shop?tab=sell");
  await page.getByRole("button", { name: /Whey protein 2 lb/ }).click();
  const scan = page.getByLabel("Scan or type a barcode");
  for (let i = 0; i < 2; i++) {
    await scan.fill(barcode);
    await scan.press("Enter");
  }
  const basket = page.getByRole("list", { name: "Basket" });
  await expect(basket.getByText("Water 1 litre")).toBeVisible();
  await expect(basket.getByText("2", { exact: true })).toBeVisible();
  await expect(page.getByText("Rs 6,560").first()).toBeVisible();
  await page.getByRole("button", { name: "Sell and take the money" }).click();
  await expect(page.getByText(/Sold\. Receipt #\d+\./)).toBeVisible();

  // The last tub is gone: the till won't sell it.
  await expect(page.getByRole("button", { name: /Whey protein 2 lb/ })).toBeDisabled();
  await expect(page.getByText("8 left")).toBeVisible();

  // Sales: the walk-in's sale, voided; the stock comes back.
  await page.getByRole("tab", { name: "Sales" }).click();
  await expect(
    page.getByText("2 × Water 1 litre, 1 × Whey protein 2 lb"),
  ).toBeVisible();
  await expect(page.getByText(/Walk-in/)).toBeVisible();
  await page
    .getByRole("listitem")
    .filter({ hasText: "Walk-in" })
    .getByRole("button", { name: "More" })
    .click();
  await page.getByRole("menuitem", { name: "Void this sale" }).click();
  const voiding = page.getByRole("dialog", { name: "Void this sale" });
  await voiding.getByLabel("Reason").fill("Rung up twice");
  await voiding.getByRole("button", { name: "Void this sale" }).click();
  await expect(page.getByText("Sale voided.")).toBeVisible();

  await page.getByRole("tab", { name: "Sell" }).click();
  await expect(page.getByRole("button", { name: /Whey protein 2 lb/ })).toBeEnabled();
  await expect(page.getByText("10 left")).toBeVisible();
});
