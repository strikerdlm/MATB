import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

import { backendCommand, frontendCommand } from "./scripts/e2e-runtime.mjs";

// Playwright loads TypeScript configs through its CommonJS transformer in
// this Next.js package, so __dirname is the portable equivalent of resolving
// the config module URL at load time.
const frontendRoot = __dirname;
const repoRoot = path.resolve(frontendRoot, "../..");
const reuseExistingServer = process.env.PW_REUSE_SERVER === "1";
const e2eRoot = path.join(repoRoot, ".suas-e2e", String(process.pid));
if (!reuseExistingServer) fs.mkdirSync(e2eRoot, { recursive: true });

const backendRoot = path.join(repoRoot, "webui", "backend");
const scenarioRoot = path.join(repoRoot, "tests", "suas", "fixtures");
const chromiumExecutable = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
  ?? (fs.existsSync("/opt/google/chrome/chrome") ? "/opt/google/chrome/chrome" : undefined);
const isolatedEnv = {
  ...process.env,
  MATB_DB_PATH: process.env.MATB_DB_PATH ?? path.join(e2eRoot, "matb-e2e.db"),
  MATB_SIMULATION_OUTPUT_DIR: process.env.MATB_SIMULATION_OUTPUT_DIR ?? path.join(e2eRoot, "exports"),
  MATB_SIMULATION_SCENARIO_DIR: scenarioRoot,
  MATB_SIMULATION_TEST_MODE: "1",
  // Keep browser tests accelerated while leaving enough real time for a
  // rendered mouse/keyboard command to settle before the next protocol gate.
  MATB_SIMULATION_WALL_TIME_SCALE: process.env.MATB_SIMULATION_WALL_TIME_SCALE ?? "0.5",
  MATB_BACKEND_PORT: "8000",
};

/**
 * Repository-owned browser gate.  Each invocation gets a process-scoped DB,
 * artifact root, and scenario directory so a developer's local session can
 * never be mistaken for the service under test.
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: process.env.PW_TEST_MATCH ?? "**/*.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["line"], ["html", { open: "never" }]] : "list",
  snapshotPathTemplate: "{testDir}/screenshots/{arg}{ext}",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:3100",
    extraHTTPHeaders: { Origin: "http://127.0.0.1:3100" },
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "off",
    launchOptions: {
      ...(chromiumExecutable ? { executablePath: chromiumExecutable } : {}),
      ...(typeof process.getuid === "function" && process.getuid() === 0 ? { args: ["--no-sandbox"] } : {}),
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
      url: "http://127.0.0.1:3100/mission/setup",
      timeout: 120_000,
      reuseExistingServer,
      env: isolatedEnv,
    },
  ],
});
