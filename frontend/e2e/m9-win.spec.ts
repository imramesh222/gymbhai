import { expect, test } from "./fixtures";
import { randomDigits, signUpGym } from "./helpers";

/** PLAN.md §16.4, 9.1, 9.2: a walk-in followed through to joining. */
test("an enquiry: trial, then convert to a member", async ({ page }) => {
  await signUpGym(page);
  const phone = `98${randomDigits(8)}`;

  await page.goto("/staff/enquiries");
  await page.getByRole("button", { name: "Add enquiry" }).first().click();
  const add = page.getByRole("dialog");
  await add.getByLabel("Full name").fill("Bikash Gurung");
  await add.getByLabel("Mobile number").fill(phone);
  await add.getByRole("button", { name: "Save enquiry" }).click();
  await expect(page.getByText("Bikash Gurung added.")).toBeVisible();

  // On the board under New; open it and note the trial visit.
  const newColumn = page.getByRole("region", { name: "New" });
  await newColumn.getByRole("button", { name: /Bikash Gurung/ }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Trial visit today" })
    .click();
  await expect(page.getByText("Trial visit noted.")).toBeVisible();
  await page.keyboard.press("Escape");
  const trialColumn = page.getByRole("region", { name: "Trial" });
  await expect(
    trialColumn.getByRole("button", { name: /Bikash Gurung/ }),
  ).toBeVisible();

  // Convert: Add member opens filled in.
  await trialColumn.getByRole("button", { name: /Bikash Gurung/ }).click();
  await page.getByRole("link", { name: "Convert to member" }).click();
  await expect(page.getByLabel("Full name")).toHaveValue("Bikash Gurung");
  await expect(page.getByLabel("Mobile number")).toHaveValue(phone);
  await page.getByLabel("Sell a membership now").uncheck();
  await page.getByRole("button", { name: "Save member" }).click();
  await expect(page.getByRole("heading", { name: /Bikash Gurung/ })).toBeVisible();

  await page.goto("/staff/enquiries");
  const joined = page.getByRole("region", { name: "Joined" });
  await expect(joined.getByRole("button", { name: /Bikash Gurung/ })).toBeVisible();
  await page.getByRole("tab", { name: "Report" }).click();
  const walkIns = page.getByRole("row", { name: /Walked in/ });
  await expect(walkIns).toContainText("100%");
});

test("the join form behind the gym QR makes an enquiry", async ({ page, browser }) => {
  const gym = await signUpGym(page);
  await page.goto("/staff/settings");
  await page.getByLabel("Let people ask to join from the gym QR").check();
  await page.getByRole("button", { name: "Save" }).first().click();
  await expect(page.getByText("Saved.", { exact: true })).toBeVisible();

  // Someone scans the poster QR without being a member.
  const visitor = await (await browser.newContext()).newPage();
  await visitor.goto(`/${gym.slug}`);
  await visitor.getByRole("link", { name: "Ask to join" }).click();
  await visitor.getByLabel("Full name").fill("Maya Tamang");
  await visitor.getByLabel("Mobile number").fill(`98${randomDigits(8)}`);
  await visitor.getByRole("button", { name: "Ask the gym to call me" }).click();
  await expect(visitor.getByText("Thanks! The gym will call you soon.")).toBeVisible();

  await page.goto("/staff/enquiries");
  await expect(
    page
      .getByRole("region", { name: "New" })
      .getByRole("button", { name: /Maya Tamang/ }),
  ).toBeVisible();
});
