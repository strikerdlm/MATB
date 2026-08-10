import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { afterEach, describe, expect, it } from "vitest";
import { verifyBundle } from "../../scripts/verify-offline.mjs";

const smsRoot = process.cwd();
const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

async function fixture(files: Readonly<Record<string, string>> = {}): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "fac-isr-offline-fixture-"));
  temporaryDirectories.push(root);
  for (const [path, contents] of Object.entries(files)) {
    const target = join(root, path);
    await mkdir(resolve(target, ".."), { recursive: true });
    await writeFile(target, contents, "utf8");
  }
  await writeFile(join(root, "bundle-manifest.json"), JSON.stringify({
    schemaVersion: "1.0",
    releaseId: "offline-fixture",
    commit: "0".repeat(40),
    builtAtUtc: "2026-08-10T00:00:00Z",
    files: [],
    image: {
      path: "images/fac-isr-sms-edge.oci.tar",
      archiveSha256: "0".repeat(64),
      manifestDigest: `sha256:${"0".repeat(64)}`,
      platform: "linux/amd64",
    },
  }), "utf8");
  return root;
}

async function verifyOffline(bundle: string) {
  const report = await verifyBundle(bundle, { noNetwork: true });
  return { status: report.ok ? 0 : 1, report };
}

describe("disconnected edge installation", () => {
  it("exposes hardened image and bundle commands", async () => {
    const packageJson = JSON.parse(await readFile(join(smsRoot, "package.json"), "utf8")) as {
      scripts?: Record<string, string>;
    };
    const dockerfile = await readFile(join(smsRoot, "Dockerfile"), "utf8");
    const compose = await readFile(join(smsRoot, "docker/compose.edge.yml"), "utf8");

    expect(packageJson.scripts).toMatchObject({
      "build:offline": "node scripts/build-offline-bundle.mjs",
      "verify:offline": "node scripts/verify-offline.mjs",
    });
    expect(dockerfile).toMatch(/node:22\.23\.2-bookworm-slim@sha256:[a-f0-9]{64}/);
    expect(dockerfile).toContain("USER 10001:10001");
    expect(compose).toContain("internal: true");
    expect(compose).toContain("read_only: true");
    expect(compose).toContain("no-new-privileges:true");
    expect(compose).toContain("/opt/sms/packages:ro");
  });

  it("fails with a named terrain check when the local package register is absent", async () => {
    const bundle = await fixture();

    const result = await verifyOffline(bundle);

    expect(result.status).toBe(1);
    expect(result.report.ok).toBe(false);
    expect(result.report.checks).toContainEqual(expect.objectContaining({
      id: "terrain-package",
      status: "fail",
    }));
  });

  it("rejects private signing material anywhere in the transfer bundle", async () => {
    const bundle = await fixture({
      "secrets/release-private.key": "-----BEGIN PRIVATE KEY-----\nfixture-only\n-----END PRIVATE KEY-----\n",
    });

    const result = await verifyOffline(bundle);

    expect(result.status).toBe(1);
    expect(result.report.checks).toContainEqual(expect.objectContaining({
      id: "private-key-material",
      status: "fail",
    }));
  });

  const image = process.env.SMS_OCI_IMAGE;
  it.skipIf(image === undefined)("starts the edge image with network access blocked", () => {
    const result = spawnSync("docker", [
      "run",
      "--rm",
      "--network",
      "none",
      "--read-only",
      "--tmpfs",
      "/tmp:rw,noexec,nosuid,size=16m",
      image!,
      "/opt/sms/bin/healthcheck",
    ], { cwd: smsRoot, encoding: "utf8" });

    expect(result.status, result.stderr).toBe(0);
    expect(result.stdout).toContain("PASS edge self-test");
  });
});
