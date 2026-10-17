import { expect, test } from "./fixtures";
import { openFromMenu, signUpGym } from "./helpers";

/** PLAN.md §16.5, 10.3–10.5: help, what's new, and telling another gym. */
test("help, what's new, and a referral link that signs a gym up", async ({
  page,
  browser,
}) => {
  const gym = await signUpGym(page);

  await openFromMenu(page, "Help and guides");
  await expect(page.getByRole("heading", { name: "Help", exact: true })).toBeVisible();
  await expect(page.getByText("Set up the door scanner")).toBeVisible();

  await openFromMenu(page, "What's new");
  await expect(page.getByRole("heading", { name: "What's new" })).toBeVisible();

  // The owner's link to share.
  await page.goto("/staff/subscription");
  const card = page.locator("section", { hasText: "Tell another gym" });
  await expect(card.getByText(`/signup?ref=${gym.slug}`)).toBeVisible();

  // Another owner signs up with it: the first gym sees them.
  const other = await (await browser.newContext()).newPage();
  const second = await signUpGym(other, "BS", `/signup?ref=${gym.slug}`);
  await page.reload();
  await expect(card.getByText(second.gymName)).toBeVisible();
  await expect(card.getByText("Signed up")).toBeVisible();
});
