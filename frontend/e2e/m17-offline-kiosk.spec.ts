import { expect, test } from "./fixtures";
import { addMember, memberSignsIn, priceOneMonthPlan, signUpGym } from "./helpers";

/**
 * PLAN.md §19.2: with the internet gone, the kiosk lets a member in from the
 * roster it saved, says so in amber, and sends the visit once it's back.
 */
test("the kiosk lets members in with no internet, and sends the visits later", async ({
  browser,
}) => {
  const deskContext = await browser.newContext();
  const desk = await deskContext.newPage();
  const gym = await signUpGym(desk, "AD");
  await priceOneMonthPlan(desk, "1500");
  const member = await addMember(desk, "Sita Rai");

  // The member's app signs the new code (gb2): a kiosk can check it offline.
  const app = await memberSignsIn(browser, gym.slug, member.phone);
  const qr = app.getByRole("img", { name: "Your check-in QR code" });
  await expect(qr).toHaveAttribute("data-qr-value", /^gb2\./);

  // A tablet at the door, registered by the owner; it fetches its roster.
  const kioskContext = await browser.newContext();
  const kiosk = await kioskContext.newPage();
  await kiosk.goto("/staff/login");
  await kiosk.getByLabel("Email or mobile number").fill(gym.phone);
  await kiosk.getByLabel("Password", { exact: true }).fill("correct-horse-battery");
  await kiosk.getByRole("button", { name: "Sign in" }).click();
  await kiosk.waitForURL("**/staff");
  const roster = kiosk.waitForResponse(
    (r) => r.url().includes("/api/v1/kiosk/roster") && r.ok(),
  );
  await kiosk.goto("/kiosk");
  await kiosk
    .getByRole("button", { name: /Use this device as the door scanner/ })
    .click();
  await expect(kiosk.getByText("Show your QR code to the camera")).toBeVisible();
  await roster;

  // The internet goes.
  await kioskContext.setOffline(true);
  await expect(
    kiosk.getByText(/No internet — letting members in from the list/),
  ).toBeVisible();
  const input = kiosk.getByLabel("Scanner input");
  await input.fill((await qr.getAttribute("data-qr-value"))!);
  await input.press("Enter");
  await expect(kiosk.getByText(/Welcome, Sita/)).toBeVisible();
  await expect(kiosk.getByText("1 visits waiting to be sent.")).toBeVisible();

  // Back online: the visit goes, the band goes.
  const sent = kiosk.waitForResponse(
    (r) => r.url().includes("/api/v1/kiosk/scans") && r.ok(),
  );
  await kioskContext.setOffline(false);
  await sent;
  await expect(kiosk.getByText(/No internet/)).toHaveCount(0);

  // The desk sees the visit on her profile.
  await desk.goto(`${member.url}?tab=visits`);
  await expect(desk.getByText("Visited: 1 days")).toBeVisible();
});
