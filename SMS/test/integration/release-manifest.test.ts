import { cp, mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { verifyRelease } from "../../scripts/generate-sbom.mjs";

interface ReleaseArtifact {
  readonly path: string;
  readonly sha256: string;
  readonly sizeBytes: number;
}

interface ReleaseManifest {
  readonly schemaVersion: "1.0";
  readonly releaseId: string;
  readonly version: string;
  readonly sourceCommit: string;
  readonly keyId: string;
  readonly publicKeySha256: string;
  readonly signature: string;
  readonly sbomPath: string;
  readonly sbomSha256: string;
  readonly scanReportPath: string;
  readonly scanReportSha256: string;
  readonly qualification: "blocked" | "approved";
  readonly operationalReady: boolean;
  readonly artifacts: readonly ReleaseArtifact[];
  readonly knownLimitations: readonly string[];
}

const repositoryRoot = join(process.cwd(), "..");
const releaseDirectory = join(repositoryRoot, "SMS/docs/release");
const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

async function readManifest(): Promise<ReleaseManifest> {
  return JSON.parse(await readFile(join(releaseDirectory, "release-manifest.json"), "utf8")) as ReleaseManifest;
}

describe("signed SMS release manifest", () => {
  it("exposes generation, signing, and verification commands", async () => {
    const packageJson = JSON.parse(await readFile(join(repositoryRoot, "SMS/package.json"), "utf8")) as {
      scripts?: Record<string, string>;
    };

    expect(packageJson.scripts).toMatchObject({
      "release:manifest": "node scripts/generate-sbom.mjs manifest",
      "release:sign": "node scripts/generate-sbom.mjs sign",
      "release:verify": "node scripts/generate-sbom.mjs verify",
    });
  });

  it("requires hashes for every artifact and a signed manifest", async () => {
    const manifest = await readManifest();
    const detached = (await readFile(join(releaseDirectory, "release-manifest.sig"), "utf8")).trim();

    expect(manifest.schemaVersion).toBe("1.0");
    expect(manifest.version).toMatch(/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/);
    expect(manifest.sourceCommit).toMatch(/^[a-f0-9]{40}$/);
    expect(manifest.keyId).toMatch(/^ed25519-sha256-[a-f0-9]{16}$/);
    expect(manifest.publicKeySha256).toMatch(/^[a-f0-9]{64}$/);
    expect(manifest.signature).toMatch(/^[A-Za-z0-9+/]+={0,2}$/);
    expect(detached).toBe(manifest.signature);
    expect(manifest.artifacts.length).toBeGreaterThan(0);
    expect(manifest.artifacts.every((artifact) => /^[a-f0-9]{64}$/.test(artifact.sha256))).toBe(true);
    expect(manifest.artifacts.every((artifact) => Number.isSafeInteger(artifact.sizeBytes) && artifact.sizeBytes >= 0)).toBe(true);
    expect(manifest.sbomSha256).toMatch(/^[a-f0-9]{64}$/);
    expect(manifest.scanReportSha256).toMatch(/^[a-f0-9]{64}$/);
    expect(manifest.artifacts).toContainEqual(expect.objectContaining({ path: manifest.sbomPath, sha256: manifest.sbomSha256 }));
    expect(manifest.artifacts).toContainEqual(expect.objectContaining({ path: manifest.scanReportPath, sha256: manifest.scanReportSha256 }));
    expect(manifest.qualification).toBe("blocked");
    expect(manifest.operationalReady).toBe(false);
    expect(manifest.knownLimitations.length).toBeGreaterThan(0);
  });

  it("verifies the pinned key, detached signature, SBOM, and artifact inventory", async () => {
    const report = await verifyRelease(repositoryRoot, { artifactSource: "source-commit" });

    expect(report.ok, JSON.stringify(report.checks, null, 2)).toBe(true);
    expect(report.operationalReady).toBe(false);
    expect(report.checks).toContainEqual(expect.objectContaining({ id: "signature", status: "pass" }));
    expect(report.checks).toContainEqual(expect.objectContaining({ id: "artifact-inventory", status: "pass" }));
    expect(report.checks).toContainEqual(expect.objectContaining({ id: "approved-security-scan", status: "warn" }));
  });

  it("detects an artifact changed after signing", async () => {
    const manifest = await readManifest();
    const fixtureRoot = await mkdtemp(join(tmpdir(), "fac-isr-release-fixture-"));
    temporaryDirectories.push(fixtureRoot);

    for (const artifact of manifest.artifacts) {
      const destination = join(fixtureRoot, artifact.path);
      await mkdir(dirname(destination), { recursive: true });
      await cp(join(repositoryRoot, artifact.path), destination);
    }
    await mkdir(join(fixtureRoot, "SMS/docs/release"), { recursive: true });
    for (const name of ["release-manifest.json", "release-manifest.sig", "release-public-key.pem"]) {
      await cp(join(releaseDirectory, name), join(fixtureRoot, "SMS/docs/release", name));
    }
    const target = manifest.artifacts.find((artifact) => artifact.path !== manifest.sbomPath && artifact.path !== manifest.scanReportPath);
    expect(target).toBeDefined();
    await writeFile(join(fixtureRoot, target!.path), "tampered after signing\n", "utf8");

    const report = await verifyRelease(fixtureRoot);

    expect(report.ok).toBe(false);
    expect(report.checks).toContainEqual(expect.objectContaining({ id: "artifact-inventory", status: "fail" }));
  });
});
