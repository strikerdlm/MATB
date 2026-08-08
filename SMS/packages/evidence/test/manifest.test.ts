import { generateKeyPairSync } from "node:crypto";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { manifestContentDigest, rejectDowngrade, sha256File, signManifest, verifyPackage } from "../src/index.js";
import type { ManifestFile, SignedPackageManifest } from "../src/index.js";

const workspaces: string[] = [];
const keys = generateKeyPairSync("ed25519");
const privateKey = keys.privateKey.export({ type: "pkcs8", format: "pem" }).toString();
const publicKey = keys.publicKey.export({ type: "spki", format: "pem" }).toString();

afterEach(async () => { await Promise.all(workspaces.splice(0).map((path) => rm(path, { recursive: true, force: true }))); });

async function fixture(): Promise<{ directory: string; manifest: SignedPackageManifest }> {
  const directory = await mkdtemp(join(tmpdir(), "fac-evidence-manifest-")); workspaces.push(directory);
  await mkdir(join(directory, "rules")); await writeFile(join(directory, "rules", "racae94.json"), "{\"Spanish\":\"regla\"}\n");
  const file: ManifestFile = { path: "rules/racae94.json", sha256: await sha256File(join(directory, "rules", "racae94.json")), sizeBytes: 21 };
  const unsigned = { schemaVersion: "1.0" as const, packageId: "fac-racae-p0", kind: "regulatory" as const, issuer: "FAC evidence staging", version: "1.0.0", issuedAtUtc: "2026-08-08T00:00:00Z", effectiveFromUtc: "2026-08-08T00:00:00Z", expiresAtUtc: "2027-08-08T00:00:00Z", geographicScope: "Colombia", contentSha256: manifestContentDigest([file]), keyId: "test-ed25519", dependencies: [], files: [file], qualification: "qualified-review" as const, caveats: ["qualified review pending"] };
  return { directory, manifest: signManifest(unsigned, privateKey) };
}

describe("offline evidence package verification", () => {
  it("rejects an altered normalized rule", async () => { const { directory, manifest } = await fixture(); await writeFile(join(directory, "rules/racae94.json"), "{\"Spanish\":\"alterada\"}\n"); expect((await verifyPackage(directory, manifest, publicKey, "2026-08-09T00:00:00Z")).ok).toBe(false); });
  it("rejects missing, extra, and tampered files", async () => {
    const { directory, manifest } = await fixture(); await rm(join(directory, "rules/racae94.json")); expect((await verifyPackage(directory, manifest, publicKey, "2026-08-09T00:00:00Z")).ok).toBe(false);
    const second = await fixture(); await writeFile(join(second.directory, "extra.txt"), "extra"); expect((await verifyPackage(second.directory, second.manifest, publicKey, "2026-08-09T00:00:00Z")).ok).toBe(false);
  });
  it("rejects invalid signature and effective-window violations", async () => {
    const { directory, manifest } = await fixture(); expect((await verifyPackage(directory, { ...manifest, signature: "AAAA" }, publicKey, "2026-08-09T00:00:00Z")).ok).toBe(false);
    expect((await verifyPackage(directory, manifest, publicKey, "2025-08-09T00:00:00Z")).ok).toBe(false); expect((await verifyPackage(directory, manifest, publicKey, "2028-08-09T00:00:00Z")).ok).toBe(false);
  });
  it("rejects dependency mismatch and path traversal manifest data", async () => {
    const { directory, manifest } = await fixture(); const dependency = { packageId: "map-baseline", version: "1.0.0", contentSha256: "a".repeat(64) }; const dependent = signManifest({ ...manifest, dependencies: [dependency], signature: "" }, privateKey); expect((await verifyPackage(directory, dependent, publicKey, "2026-08-09T00:00:00Z")).ok).toBe(false);
    expect(() => signManifest({ ...manifest, files: [{ ...manifest.files[0], path: "../escape" }], contentSha256: manifest.contentSha256 }, privateKey)).toThrow("traversal");
  });
  it("rejects a package older than the installed version", async () => { const { manifest } = await fixture(); const older = signManifest({ ...manifest, version: "0.9.0", signature: "" }, privateKey); expect(() => rejectDowngrade(manifest, older)).toThrow("downgrade"); });
  it("rejects an older effective period even when semantic version increases", async () => {
    const { manifest } = await fixture();
    const stale = signManifest({ ...manifest, version: "2.0.0", issuedAtUtc: "2026-08-07T00:00:00Z", effectiveFromUtc: "2026-08-07T00:00:00Z", signature: "" }, privateKey);
    expect(() => rejectDowngrade(manifest, stale)).toThrow("effective period");
  });
  it("requires a caller-supplied exact UTC as-of time", async () => {
    const { directory, manifest } = await fixture();
    const report = await verifyPackage(directory, manifest, publicKey, undefined as unknown as string);
    expect(report.ok).toBe(false); expect(report.checks).toContainEqual(expect.objectContaining({ id: "as-of", status: "fail" }));
  });
  it("rejects unsupported manifest kinds and missing geographic scope", async () => {
    const { manifest } = await fixture();
    expect(() => signManifest({ ...manifest, kind: "unknown" as SignedPackageManifest["kind"], signature: "" }, privateKey)).toThrow("kind");
    expect(() => signManifest({ ...manifest, geographicScope: "", signature: "" }, privateKey)).toThrow("geographicScope");
  });
});
