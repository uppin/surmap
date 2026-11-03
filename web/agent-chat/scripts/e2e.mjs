// Runs the Playwright suite, or skips it with a note when no Chromium is installed here.
// CI installs the browser and sets E2E_REQUIRE_BROWSER=1, which turns the skip into a failure.
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { chromium } from "@playwright/test";

const executable = chromium.executablePath();
if (!existsSync(executable)) {
  const reason = `no Playwright Chromium at ${executable}; install it with \`yarn playwright install chromium\``;
  if (process.env.E2E_REQUIRE_BROWSER === "1") {
    console.error(`e2e: failed: ${reason}`);
    process.exit(1);
  }
  console.log(`e2e: skipped: ${reason}`);
  process.exit(0);
}

const run = spawnSync("playwright", ["test", ...process.argv.slice(2)], { stdio: "inherit" });
process.exit(run.status ?? 1);
