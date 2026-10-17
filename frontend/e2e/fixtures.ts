import { expect, test as base } from "@playwright/test";

/**
 * Every test fails if any page it opened broke the Content-Security-Policy
 * (src/lib/csp.ts): a blocked script only says so in the console, and the
 * page may look fine until someone taps the thing that needed it.
 */
export const test = base.extend<{ cspGuard: void; fitsThePhone: void }>({
  cspGuard: [
    async ({ context }, use) => {
      const violations: string[] = [];
      const watch = (page: import("@playwright/test").Page) =>
        page.on("console", (message) => {
          const text = message.text();
          if (/Content Security Policy|Refused to (load|execute|apply)/.test(text))
            violations.push(`${page.url()}: ${text}`);
        });
      context.pages().forEach(watch);
      context.on("page", watch);
      await use();
      expect(violations, "Content-Security-Policy violations").toEqual([]);
    },
    { auto: true },
  ],
  // On a phone, no page scrolls sideways: whatever is open when the test ends
  // must fit the screen's width.
  fitsThePhone: [
    async ({ context }, use, testInfo) => {
      await use();
      if (testInfo.project.name !== "phone") return;
      for (const page of context.pages()) {
        if (page.isClosed() || !page.url().startsWith("http")) continue;
        const { scroll, screen } = await page.evaluate(() => ({
          scroll: document.documentElement.scrollWidth,
          screen: window.innerWidth,
        }));
        expect(scroll, `${page.url()} is wider than the phone`).toBeLessThanOrEqual(
          screen + 1,
        );
      }
    },
    { auto: true },
  ],
});

export { expect };
