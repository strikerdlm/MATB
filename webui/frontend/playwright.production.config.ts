import { defineConfig } from "@playwright/test";
import swarm from "./playwright.swarm.config";

// Reuse isolated production services and non-default ports. Never attach these
// checks to an operator's running console or research database.
export default defineConfig({
  ...swarm,
  testMatch: ["swarm.spec.ts", "production-smoke.spec.ts", "experiment-designer.spec.ts"],
  outputDir: "test-results/production",
});
