import { expect, test } from "./fixtures";
import { addMember, memberSignsIn, priceOneMonthPlan, signUpGym } from "./helpers";

/** Tomorrow, in Nepal: its weekday, 0 being Monday as the timetable has it. */
function tomorrowInNepal(): number {
  const nepal = new Date(Date.now() + (5 * 60 + 45) * 60_000 + 86_400_000);
  return (nepal.getUTCDay() + 6) % 7;
}

/**
 * PLAN.md §19.4: a class and its timetable, a member booking it in the app,
 * the waitlist when it's full, and a place freed going to the first in line.
 */
test("classes: book from the app, a waitlist, a place passed on", async ({
  page,
  browser,
}) => {
  const gym = await signUpGym(page, "AD");
  await priceOneMonthPlan(page, "1500");

  // Settings › Classes: a Zumba class with one place, tomorrow at 18:00.
  await page.goto("/staff/settings/classes");
  await page.getByRole("button", { name: "Add a class" }).click();
  const kind = page.getByRole("dialog", { name: "Add a class" });
  await kind.getByLabel("Name").fill("Zumba");
  await kind.getByLabel("Places").fill("1");
  await kind.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: /Zumba · 60 min/ })).toBeVisible();
  await page.getByRole("button", { name: "Add to the timetable" }).click();
  const slot = page.getByRole("dialog", { name: "Add to the timetable" });
  await slot.getByLabel("Day").selectOption(String(tomorrowInNepal()));
  await slot.getByLabel("Starts").fill("18:00");
  await slot.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: /18:00\s*Zumba/ })).toBeVisible();

  const sita = await addMember(page, "Sita Rai");
  await addMember(page, "Hari Thapa");

  // Sita books the only place from her app.
  const app = await memberSignsIn(browser, gym.slug, sita.phone);
  await app.getByRole("link", { name: /Book a class/ }).click();
  await expect(app.getByRole("heading", { name: "Classes" })).toBeVisible();
  await expect(app.getByText("1 places left")).toBeVisible();
  await app.getByRole("button", { name: "Book" }).click();
  await expect(app.getByText("You're booked")).toBeVisible();

  // The desk: the class is full; Hari goes on the waitlist.
  await page.goto("/staff/classes");
  await page.getByRole("button", { name: /Zumba/ }).first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Sita Rai")).toBeVisible();
  await dialog.getByLabel("Book a member").fill("Hari");
  await dialog.getByRole("button", { name: /Hari Thapa/ }).click();
  await dialog.getByRole("button", { name: "Book", exact: true }).click();
  const hariRow = dialog.getByRole("listitem").filter({ hasText: "Hari Thapa" });
  await expect(hariRow.getByText(/Waitlist/)).toBeVisible();

  // Sita can't come after all: her place goes to Hari, live on the desk.
  await app.getByRole("button", { name: "Cancel" }).click();
  await expect(app.getByText(/places left|Full/)).toBeVisible();
  const hariNow = page
    .getByRole("dialog")
    .getByRole("listitem")
    .filter({ hasText: "Hari Thapa" });
  await expect(hariNow).toBeVisible();
  await expect(hariNow.getByText(/Waitlist/)).toHaveCount(0);
  await expect(
    page.getByRole("dialog").getByRole("listitem").filter({ hasText: "Sita Rai" }),
  ).toHaveCount(0);
});
