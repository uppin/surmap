import { defineConfig, devices } from "@playwright/test";

const PORT = 5179;

/**
 * Playwright against the Vite dev server; each test starts its own stub agent server
 * (`e2e/stub-chat-server.ts`) and points the page at it with `?server=`.
 * Run through `yarn e2e`, which skips when no Chromium is installed.
 */
export default defineConfig({
  testDir: "e2e",
  workers: 1,
  timeout: 30_000,
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `yarn dev --host 127.0.0.1 --port ${PORT} --strictPort`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: !process.env.CI,
  },
});
