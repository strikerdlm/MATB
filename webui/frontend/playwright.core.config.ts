import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

import { backendCommand, frontendCommand } from "./scripts/e2e-runtime.mjs";

const frontendRoot = __dirname;
const repoRoot = path.resolve(frontendRoot, "../..");
const backendRoot = path.join(repoRoot, "webui", "backend");
const reuseExistingServer = process.env.PW_REUSE_SERVER === "1";
const runRoot = path.join(repoRoot, ".matb-core-e2e", String(process.pid));
if (!reuseExistingServer) fs.mkdirSync(runRoot, { recursive: true });

const chromiumExecutable = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
  ?? (fs.existsSync("/opt/google/chrome/chrome") ? "/opt/google/chrome/chrome" : undefined);
const isolatedEnv = {
  ...process.env,
  MATB_COMPONENTS: "core",
  MATB_DB_PATH: process.env.MATB_DB_PATH ?? path.join(runRoot, "matb-core-e2e.db"),
};

export default defineConfig({
  testDir: "./e2e",
  testMatch: "experiment-designer.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "line" : "list",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:3100",
    extraHTTPHeaders: { Origin: "http://127.0.0.1:3100" },
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    launchOptions: {
      ...(chromiumExecutable ? { executablePath: chromiumExecutable } : {}),
      ...(typeof process.getuid === "function" && process.getuid() === 0
        ? { args: ["--no-sandbox"] }
        : {}),
    },
  },
  webServer: [
    {
      command: backendCommand(),
      cwd: backendRoot,
      url: "http://127.0.0.1:8000/health",
      timeout: 120_000,
      reuseExistingServer,
      env: isolatedEnv,
    },
    {
      command: frontendCommand(frontendRoot),
      cwd: frontendRoot,
      url: "http://127.0.0.1:3100/experiments",
      timeout: 120_000,
      reuseExistingServer,
      env: isolatedEnv,
    },
  ],
});
