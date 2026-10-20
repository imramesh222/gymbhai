import { expect, test } from "./fixtures";
import { priceOneMonthPlan, randomDigits, signUpGym } from "./helpers";

/** Where a reader reaches the API: the readers call it directly, not the web. */
const API =
  process.env.E2E_API_URL ?? `http://localhost:${process.env.API_PORT ?? "8000"}`;

/** "2026-10-20 06:15:22", Nepal time, as a ZKTeco reader reports a scan. */
function readerTime(at: Date): string {
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Kathmandu",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(at);
}

/**
 * PLAN.md §18.2: a ZKTeco reader added in Settings, its members put on it,
 * and a fingerprint at the door a visit. The reader is played here, speaking
 * ADMS to the API as one would.
 */
test("a fingerprint reader: added, its members on it, a scan a visit", async ({
  page,
  request,
}) => {
  await signUpGym(page, "AD");
  await priceOneMonthPlan(page, "1500");
  await page.goto("/staff/members/new");
  await page.getByLabel("Full name").fill("Hari Thapa");
  await page.getByLabel("Mobile number").fill(`98${randomDigits(8)}`);
  await page.getByLabel("Plan").selectOption({ label: "1 month — Rs 1,500" });
  await page.getByRole("button", { name: "Save member" }).click();
  await expect(page.getByRole("heading", { name: /Hari Thapa/ })).toBeVisible();

  // Settings → Door scanners: a ZKTeco reader, known by its serial number.
  const serial = `E2E${randomDigits(9)}`;
  await page.goto("/staff/settings/door");
  await page.getByRole("button", { name: "Add a fingerprint or face reader" }).click();
  const dialog = page.getByRole("dialog", { name: "Add a fingerprint or face reader" });
  await dialog.getByLabel("Name").fill("Front door");
  await dialog.getByLabel("Serial number").fill(serial);
  await dialog
    .getByRole("button", { name: "Add a fingerprint or face reader" })
    .click();
  await expect(dialog.getByText(/Cloud Server Setting \(ADMS\)/)).toBeVisible();
  // The button under the steps; the ✕ in the corner is "Close" too.
  await dialog.getByText("Close", { exact: true }).click();

  // The reader starts, and collects its members.
  const started = await request.get(`${API}/iclock/cdata?SN=${serial}&options=all`);
  expect(await started.text()).toContain(`GET OPTION FROM: ${serial}`);
  const waiting = await (
    await request.get(`${API}/iclock/getrequest?SN=${serial}`)
  ).text();
  expect(waiting).toContain("Name=Hari Thapa");
  const [, id, pin] = /C:(\d+):DATA UPDATE USERINFO PIN=(\d+)/.exec(waiting) ?? [];
  const done = await request.post(`${API}/iclock/devicecmd?SN=${serial}`, {
    data: `ID=${id}&Return=0&CMD=DATA\n`,
  });
  expect(await done.text()).toBe("OK");

  // A fingerprint at the door: Hari's visit, under the same rules as a QR.
  const scan = `${pin}\t${readerTime(new Date(Date.now() + 2000))}\t0\t1\t0\t0\t0`;
  const sent = await request.post(
    `${API}/iclock/cdata?SN=${serial}&table=ATTLOG&Stamp=1`,
    { data: `${scan}\n` },
  );
  expect(await sent.text()).toBe("OK: 1");
  await page.goto("/staff");
  const inside = page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: "Probably inside now" }) });
  await expect(inside.getByRole("link", { name: "Hari Thapa" })).toBeVisible();

  // The reader's list says so, and Hari's profile has his number on it.
  await page.goto("/staff/settings/door");
  await expect(page.getByText(/1 on the reader · 0 waiting/)).toBeVisible();
  await page.goto("/staff/members");
  await page
    .getByRole("link", { name: /Hari Thapa/ })
    .first()
    .click();
  await expect(page.getByText("Door reader number")).toBeVisible();
});
