import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

// Playwright loads TypeScript configs through its CommonJS transformer in
// this Next.js package, so __dirname is the portable equivalent of resolving
// the config module URL at load time.
const frontendRoot = __dirname;
const repoRoot = path.resolve(frontendRoot, "../..");
const e2eRoot = path.join(repoRoot, ".suas-e2e", String(process.pid));
fs.mkdirSync(e2eRoot, { recursive: true });

const backendRoot = path.join(repoRoot, "webui", "backend");
const scenarioRoot = path.join(repoRoot, "tests", "suas", "fixtures");
const pythonFromEnv = process.env.MATB_PYTHON
  ?? (process.env.MATB_VENV ? path.join(process.env.MATB_VENV, "bin", "python") : undefined);
const pythonExecutable = pythonFromEnv && fs.existsSync(pythonFromEnv) ? pythonFromEnv : "python3";
const chromiumExecutable = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
  ?? (fs.existsSync("/opt/google/chrome/chrome") ? "/opt/google/chrome/chrome" : undefined);
const reuseExistingServer = process.env.PW_REUSE_SERVER === "1";

const isolatedEnv = {
  ...process.env,
  MATB_DB_PATH: path.join(e2eRoot, "matb-e2e.db"),
  MATB_SIMULATION_OUTPUT_DIR: path.join(e2eRoot, "exports"),
  MATB_SIMULATION_SCENARIO_DIR: scenarioRoot,
  MATB_SIMULATION_TEST_MODE: "1",
  MATB_SIMULATION_WALL_TIME_SCALE: "0.1",
  MATB_BACKEND_PORT: "8000",
};

/**
 * Repository-owned browser gate.  Each invocation gets a process-scoped DB,
 * artifact root, and scenario directory so a developer's local session can
 * never be mistaken for the service under test.
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["line"], ["html", { open: "never" }]] : "list",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:3100",
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
      command: `${pythonExecutable} -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
      cwd: backendRoot,
      url: "http://127.0.0.1:8000/health",
      timeout: 120_000,
      reuseExistingServer,
      env: isolatedEnv,
    },
    {
      command: "npm run dev",
      cwd: frontendRoot,
      url: "http://127.0.0.1:3100/mission/setup",
      timeout: 120_000,
      reuseExistingServer,
      env: isolatedEnv,
    },
  ],
});
