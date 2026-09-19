import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against a running stack: `make up`, then `make e2e`.
 * CI starts the API and a production build of the web app first.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  // A dev server compiles each page on its first visit; the longer flows
  // cross a dozen pages and three browsers.
  timeout: 60_000,
  expect: { timeout: 15_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    // Staff and members mostly use phones.
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
});
