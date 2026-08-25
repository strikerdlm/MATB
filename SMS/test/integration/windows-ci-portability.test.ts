import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import playwrightConfig from "../../apps/console/playwright.config.js";

const smsRoot = process.cwd();

async function source(path: string): Promise<string> {
  return readFile(join(smsRoot, path), "utf8");
}

describe("Windows CI portability policy", () => {
  it("lets Playwright resolve its installed Chromium executable", () => {
    const use = playwrightConfig.use as { launchOptions?: { executablePath?: string } } | undefined;

    expect(use?.launchOptions?.executablePath).toBeUndefined();
  });

  it("uses host-native temporary and file URL paths in the console gates", async () => {
    const harness = await source("apps/console/e2e/live-edge-harness.mjs");
    const consoleSpec = await source("apps/console/e2e/console.spec.ts");
    const config = await source("apps/console/playwright.config.ts");

    expect(harness).toContain("fileURLToPath(new URL(\"../dist/\", import.meta.url))");
    expect(harness).not.toMatch(/["']\/tmp\//u);
    expect(consoleSpec).not.toMatch(/["']\/tmp\//u);
    expect(consoleSpec).toContain("join(tmpdir(),");
    expect(config).toContain("SMS_PLAYWRIGHT_EXECUTABLE_PATH");
    expect(config).not.toMatch(/\/root\/|linux64/u);
  });

  it("keeps cross-platform tests enabled while explicitly excluding POSIX-only cases on Windows", async () => {
    const platformBundles = await source("test/integration/platform-bundles.test.ts");
    const technicalRelease = await source("test/integration/technical-release.test.ts");
    const evidencePackage = await source("tools/research/test/package.test.ts");
    const evidencePackageLock = await source("tools/research/test/package-lock.test.ts");
    const admin = await source("apps/edge-api/test/admin.test.ts");
    const packages = await source("apps/edge-api/test/packages.test.ts");

    expect(platformBundles).toContain('test.skipIf(isWindows)("cold-starts the Linux bundle');
    expect(platformBundles).toContain('describe.skipIf(isWindows)("Linux native lifecycle"');
    expect(platformBundles).toContain('describe.skipIf(isWindows)("OCI privileged init');
    expect(platformBundles).toContain('["win32-x64", "TEST-ONLY-fac-isr-sms-0.2.0-rc.1-win32-x64.zip"]');
    expect(technicalRelease).toContain('it.skipIf(isWindows)("rejects native special entries');
    expect(evidencePackage).toContain('describe.skipIf(isWindows)("deterministic evidence package assembly"');
    expect(evidencePackage).toContain('describe("evidence package contracts"');
    expect(evidencePackageLock).toContain('describe.skipIf(isWindows)("publish-lock cleanup"');
    expect(admin).toContain('it("runs backup create, verify, restore, and diagnose offline"');
    expect(admin).toContain('it.skipIf(isWindows)("enforces POSIX password-file modes');
    expect(packages).toContain('it("rejects a package root symlink that escapes');
  });
});
