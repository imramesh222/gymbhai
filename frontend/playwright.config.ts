import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against a running stack: `make up`, then `make e2e`.
 * CI starts the API and a production build of the web app first.
 */
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  // Outside frontend/: the dev server watches that folder, and traces written
  // into it made it recompile mid-run, stalling every test after a failure.
  outputDir: "../.e2e/test-results",
  fullyParallel: true,
  // A dev server compiles each page on its first visit; the longer flows
  // cross a dozen pages and three browsers.
  timeout: 60_000,
  expect: { timeout: 15_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI
    ? [["list"], ["html", { open: "never", outputFolder: "../.e2e/report" }]]
    : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    // For the production stack on https://localhost, whose certificate comes
    // from Caddy's local authority.
    ignoreHTTPSErrors: Boolean(process.env.E2E_IGNORE_HTTPS),
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    // Staff and members mostly use phones.
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
});
