import { defineConfig } from "@playwright/test";

import baseConfig from "./playwright.config";

/** Focused visual-profile browser gate with the repository-managed services. */
export default defineConfig(baseConfig, {
  testMatch: "openmatb-appearance.spec.ts",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
});
