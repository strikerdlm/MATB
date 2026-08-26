import { defineConfig } from "@playwright/test";

const configuredExecutable = process.env.SMS_PLAYWRIGHT_EXECUTABLE_PATH?.trim();

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "line",
  use: {
    baseURL: "https://127.0.0.1:4173",
    ignoreHTTPSErrors: true,
    ...(configuredExecutable === undefined || configuredExecutable === ""
      ? {}
      : { launchOptions: { executablePath: configuredExecutable } }),
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run harness:e2e",
    url: "https://127.0.0.1:4173/healthz",
    ignoreHTTPSErrors: true,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
