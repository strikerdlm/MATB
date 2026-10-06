import { defineConfig } from "vitest/config";
import { createHash } from "node:crypto";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = fileURLToPath(new URL(".", import.meta.url));
const cacheKey = createHash("sha256")
  .update(`${frontendRoot}\0${os.userInfo().username}`)
  .digest("hex")
  .slice(0, 20);

export default defineConfig({
  // Keep account-specific test results out of npm ci's dependency cleanup.
  cacheDir: path.join(os.tmpdir(), `matb-vitest-${cacheKey}`),
  resolve: { alias: { "@": path.resolve(frontendRoot, "src") } },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx", "e2e/**/*.test.ts"],
    setupFiles: ["src/test/setup.ts"],
  },
});
