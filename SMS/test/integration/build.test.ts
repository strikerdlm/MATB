import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

interface RootPackageJson {
  readonly version?: string;
  readonly scripts?: Record<string, string>;
  readonly engines?: Record<string, string>;
}

function readPackageJson(): RootPackageJson {
  return JSON.parse(readFileSync(resolve(process.cwd(), "package.json"), "utf8")) as RootPackageJson;
}

function readWorkspaceConfig(): string {
  return readFileSync(resolve(process.cwd(), "vitest.workspace.ts"), "utf8");
}

function readCiWorkflow(): string {
  return readFileSync(resolve(process.cwd(), "../.github/workflows/sms-ci.yml"), "utf8");
}

function readReleaseWorkflow(): string {
  return readFileSync(resolve(process.cwd(), "../.github/workflows/sms-release.yml"), "utf8");
}

describe("release verification command", () => {
  it("requires every foundational verification script", () => {
    expect(readPackageJson().scripts).toMatchObject({
      build: expect.any(String),
      "build:apps": expect.any(String),
      "build:packages": expect.any(String),
      "build:tools": expect.any(String),
      typecheck: expect.any(String),
      test: expect.any(String),
      lint: expect.any(String),
      "verify:all": expect.any(String),
      "verify:matrix": expect.any(String),
      "verify:acceptance": expect.any(String),
      "verify:no-c2": expect.any(String),
      "verify:data-separation": expect.any(String),
      "verify:ci": expect.any(String),
      "verify:technical-release": expect.any(String),
      "verify:operational": expect.any(String),
    });
    expect(readPackageJson().scripts?.["verify:all"]).toContain("verify:matrix");
    expect(readPackageJson().scripts?.["verify:all"]).toContain("verify:acceptance");
  });

  it("pins CI and local verification to Node 22", () => {
    expect(readPackageJson().engines?.node).toBe("22.x");
  });

  it("has a semantic release identity for SBOM package URLs", () => {
    expect(readPackageJson().version).toMatch(/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/);
  });

  it("discovers package, app, tool, and root integration tests", () => {
    const workspace = readWorkspaceConfig();

    expect(workspace).toContain('"packages/*"');
    expect(workspace).toContain('"apps/*"');
    expect(workspace).toContain('"tools/*"');
    expect(workspace).toContain('include: ["test/**/*.test.ts"]');
  });

  it("runs exact Linux and Windows candidate gates from clean Node 22.23.2 GitHub jobs", () => {
    const workflow = readCiWorkflow();

    expect(workflow).toMatch(/actions\/checkout@[a-f0-9]{40}/);
    expect(workflow).toMatch(/actions\/setup-node@[a-f0-9]{40}/);
    expect(workflow).toContain("fetch-depth: 0");
    expect(workflow).toContain("NODE_VERSION: 22.23.2");
    expect(workflow).toContain("ubuntu-24.04");
    expect(workflow).toContain("windows-2022");
    expect(workflow).toContain("npm ci");
    expect(workflow).toContain("npx playwright install --with-deps chromium");
    expect(workflow).toContain("SHASUMS256.txt.asc");
    expect(workflow).toContain("--runtime-checksums-signature");
    expect(workflow).toContain("--node-release-keyring");
    expect(workflow).toContain("npm run verify:ci -- --platform linux");
    expect(workflow).toContain("npm run verify:ci -- --platform windows");
    expect(workflow).toContain("fac-isr-sms-${RELEASE_VERSION}-linux-x64.tar.gz");
    expect(workflow).toContain("fac-isr-sms-$env:RELEASE_VERSION-win32-x64.zip");
    expect(workflow).toContain("fac-isr-sms-${RELEASE_VERSION}-linux-amd64.oci.tar");
    expect(workflow.indexOf("npm run verify:ci -- --platform linux")).toBeLessThan(workflow.indexOf("Upload Ubuntu evidence only after gates"));
    expect(workflow.indexOf("npm run verify:ci -- --platform windows")).toBeLessThan(workflow.indexOf("Upload Windows evidence only after gates"));
    expect(workflow).toContain("working-directory: SMS");
  });

  it("publishes only an externally signed technical candidate while operational readiness stays blocked", () => {
    const workflow = readReleaseWorkflow();

    expect(workflow).toContain("workflow_dispatch:");
    expect(workflow).toContain('tags: ["sms-v0.2.0-rc.1"]');
    expect(workflow).toContain("SMS_RELEASE_SIGNATURE_B64");
    expect(workflow).toContain("SMS_RELEASE_PUBLIC_KEY_B64");
    expect(workflow).not.toMatch(/PRIVATE_KEY|private-key/u);
    expect(workflow).toContain("npm run verify:technical-release");
    expect(workflow).toContain("npm run verify:operational -- --require-ready");
    expect(workflow.indexOf("npm run verify:technical-release")).toBeLessThan(workflow.indexOf("actions/upload-artifact@"));
  });
});
