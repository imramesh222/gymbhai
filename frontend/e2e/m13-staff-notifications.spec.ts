import { expect, test } from "./fixtures";
import { signUpGym } from "./helpers";

/** PLAN.md §18.6: offered once on Today, chosen in My account. */
test("staff notifications: offered once, chosen in My account", async ({
  page,
  context,
}) => {
  // Headless Chromium always says notifications are "denied"; a browser that
  // was never asked says "default".
  await context.addInitScript(() =>
    Object.defineProperty(Notification, "permission", { get: () => "default" }),
  );
  await signUpGym(page);

  // Today offers it once; "Not now" puts it away.
  const prompt = page.getByRole("region", { name: "Get notified on this device" });
  await expect(prompt).toBeVisible();
  await prompt.getByRole("button", { name: "Not now" }).click();
  await expect(prompt).toHaveCount(0);

  // My account: off here, and the owner may get all three.
  await page.goto("/staff/profile");
  await expect(page.getByText("Off for this phone or computer.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Turn on" })).toBeVisible();
  const enquiries = page.getByRole("checkbox", {
    name: "Enquiries from the join form",
  });
  await expect(enquiries).toBeChecked();
  await expect(
    page.getByRole("checkbox", { name: "Payments sent from the app, to approve" }),
  ).toBeChecked();

  // A kind turned off is kept, for every device of theirs.
  const saved = page.waitForResponse(
    (r) => r.url().includes("/api/v1/auth/me/notifications") && r.ok(),
  );
  await enquiries.uncheck();
  await saved;
  await page.reload();
  await expect(
    page.getByRole("checkbox", { name: "Enquiries from the join form" }),
  ).not.toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Freeze requests" })).toBeChecked();

  // Put away on Today, it stays put away.
  await page.goto("/staff");
  await expect(page.getByRole("heading", { name: /Welcome/ })).toBeVisible();
  await expect(prompt).toHaveCount(0);
});
