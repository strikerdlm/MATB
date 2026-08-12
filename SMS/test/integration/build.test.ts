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
      "verify:no-c2": expect.any(String),
      "verify:data-separation": expect.any(String),
    });
    expect(readPackageJson().scripts?.["verify:all"]).toContain("verify:matrix");
  });

  it("pins CI and local verification to Node 22", () => {
    expect(readPackageJson().engines?.node).toBe("22.x");
  });

  it("has a semantic release identity for SBOM package URLs", () => {
    expect(readPackageJson().version).toMatch(/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/);
  });

  it("discovers package, app, tool, and root integration tests", () => {
    const workspace = readWorkspaceConfig();

    expect(workspace).toContain('"packages/*"');
    expect(workspace).toContain('"apps/*"');
    expect(workspace).toContain('"tools/*"');
    expect(workspace).toContain('include: ["test/**/*.test.ts"]');
  });

  it("runs the release gate from a clean Node 22 GitHub job", () => {
    const workflow = readCiWorkflow();

    expect(workflow).toMatch(/actions\/checkout@[a-f0-9]{40}/);
    expect(workflow).toMatch(/actions\/setup-node@[a-f0-9]{40}/);
    expect(workflow).toContain("fetch-depth: 0");
    expect(workflow).toContain("node-version: 22");
    expect(workflow).toContain("npm ci");
    expect(workflow).toContain("npx playwright install --with-deps chromium");
    expect(workflow).toContain("npm run verify:all");
    expect(workflow).toContain("npm run build:offline -- --output dist/offline-bundle");
    expect(workflow).toContain("npm run verify:offline -- --bundle dist/offline-bundle --no-network");
    expect(workflow).toContain("SMS_OCI_IMAGE: fac-isr-sms-edge:offline");
    expect(workflow.indexOf("npm run build:offline -- --output dist/offline-bundle")).toBeLessThan(workflow.indexOf("npm run verify:all"));
    expect(workflow).toContain("working-directory: SMS");
  });
});
