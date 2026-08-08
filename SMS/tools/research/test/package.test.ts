import { generateKeyPairSync } from "node:crypto";
import { lstat, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { verifyPackage } from "@fac-isr/evidence";
import { assembleEvidencePackage, explicitPrivateKey, readSignedManifest } from "../src/package.js";
import { requiredVerificationAsOf } from "../src/cli.js";

const paths: string[] = [];
const pair = generateKeyPairSync("ed25519");
const privateKey = pair.privateKey.export({ type: "pkcs8", format: "pem" }).toString();
const publicKey = pair.publicKey.export({ type: "spki", format: "pem" }).toString();
afterEach(async () => { await Promise.all(paths.splice(0).map((path) => rm(path, { recursive: true, force: true }))); });

describe("deterministic evidence package assembly", () => {
  it("builds a closed signed package from explicit staging key material", async () => {
    const root = await mkdtemp(join(tmpdir(), "fac-evidence-source-")); const outputParent = await mkdtemp(join(tmpdir(), "fac-evidence-output-")); const output = join(outputParent, "package"); paths.push(root, outputParent);
    await writeFile(join(root, "rule.json"), "{\"rule\":true}\n");
    const manifest = await assembleEvidencePackage({ sourceRoot: root, outputDirectory: output, files: [{ sourcePath: "rule.json", packagePath: "content/rule.json" }], privateKey, manifest: { schemaVersion: "1.0", packageId: "fac-package-test", kind: "regulatory", issuer: "test issuer", version: "1.0.0", issuedAtUtc: "2026-08-08T00:00:00Z", effectiveFromUtc: "2026-08-08T00:00:00Z", expiresAtUtc: "2027-08-08T00:00:00Z", geographicScope: "Colombia", keyId: "test", dependencies: [], qualification: "qualified-review", caveats: ["test only"] } });
    expect(await readSignedManifest(join(output, "evidence-package-manifest.json"))).toEqual(manifest);
    expect((await verifyPackage(output, manifest, publicKey, "2026-08-09T00:00:00Z")).ok).toBe(true);
    expect((await readFile(join(output, "evidence-package-manifest.sig"), "utf8")).trim()).toBe(manifest.signature);
  });
  it("refuses to erase an existing caller-selected output directory", async () => {
    const root = await mkdtemp(join(tmpdir(), "fac-evidence-source-")); const output = await mkdtemp(join(tmpdir(), "fac-evidence-output-")); paths.push(root, output);
    await writeFile(join(root, "rule.json"), "{}\n"); await writeFile(join(output, "preserve.txt"), "do-not-delete");
    await expect(assembleEvidencePackage({ sourceRoot: root, outputDirectory: output, files: [{ sourcePath: "rule.json" }], privateKey, manifest: { schemaVersion: "1.0", packageId: "fac-package-test", kind: "regulatory", issuer: "test issuer", version: "1.0.0", issuedAtUtc: "2026-08-08T00:00:00Z", effectiveFromUtc: "2026-08-08T00:00:00Z", geographicScope: "Colombia", keyId: "test", dependencies: [], qualification: "qualified-review", caveats: ["test only"] } })).rejects.toThrow("already exists");
    await expect(readFile(join(output, "preserve.txt"), "utf8")).resolves.toBe("do-not-delete");
  });
  it("refuses source-root output selection before any filesystem mutation", async () => {
    const root = await mkdtemp(join(tmpdir(), "fac-evidence-source-")); paths.push(root); await writeFile(join(root, "rule.json"), "{}\n");
    await expect(assembleEvidencePackage({ sourceRoot: root, outputDirectory: root, files: [{ sourcePath: "rule.json" }], privateKey, manifest: { schemaVersion: "1.0", packageId: "fac-package-test", kind: "regulatory", issuer: "test issuer", version: "1.0.0", issuedAtUtc: "2026-08-08T00:00:00Z", effectiveFromUtc: "2026-08-08T00:00:00Z", geographicScope: "Colombia", keyId: "test", dependencies: [], qualification: "qualified-review", caveats: ["test only"] } })).rejects.toThrow("sourceRoot");
    await expect(readFile(join(root, "rule.json"), "utf8")).resolves.toBe("{}\n");
  });
  it("validates manifest input before creating a new output directory", async () => {
    const root = await mkdtemp(join(tmpdir(), "fac-evidence-source-")); const outputParent = await mkdtemp(join(tmpdir(), "fac-evidence-output-")); const output = join(outputParent, "package"); paths.push(root, outputParent); await writeFile(join(root, "rule.json"), "{}\n");
    await expect(assembleEvidencePackage({ sourceRoot: root, outputDirectory: output, files: [{ sourcePath: "rule.json" }], privateKey, manifest: { schemaVersion: "1.0", packageId: "fac-package-test", kind: "invalid" as "regulatory", issuer: "test issuer", version: "1.0.0", issuedAtUtc: "2026-08-08T00:00:00Z", effectiveFromUtc: "2026-08-08T00:00:00Z", geographicScope: "Colombia", keyId: "test", dependencies: [], qualification: "qualified-review", caveats: ["test only"] } })).rejects.toThrow("kind");
    await expect(lstat(output)).rejects.toMatchObject({ code: "ENOENT" });
  });
  it("rejects symlink source files rather than following them into the package", async () => {
    const root = await mkdtemp(join(tmpdir(), "fac-evidence-source-")); const outputParent = await mkdtemp(join(tmpdir(), "fac-evidence-output-")); const output = join(outputParent, "package"); paths.push(root, outputParent);
    await writeFile(join(root, "secret.txt"), "not-for-package"); await symlink(join(root, "secret.txt"), join(root, "rule.json"));
    await expect(assembleEvidencePackage({ sourceRoot: root, outputDirectory: output, files: [{ sourcePath: "rule.json" }], privateKey, manifest: { schemaVersion: "1.0", packageId: "fac-package-test", kind: "regulatory", issuer: "test issuer", version: "1.0.0", issuedAtUtc: "2026-08-08T00:00:00Z", effectiveFromUtc: "2026-08-08T00:00:00Z", geographicScope: "Colombia", keyId: "test", dependencies: [], qualification: "qualified-review", caveats: ["test only"] } })).rejects.toThrow("non-symlink");
    await expect(readFile(join(root, "secret.txt"), "utf8")).resolves.toBe("not-for-package");
  });
  it("validates untrusted manifest JSON before returning it", async () => {
    const root = await mkdtemp(join(tmpdir(), "fac-evidence-manifest-")); paths.push(root); const path = join(root, "manifest.json");
    await writeFile(path, JSON.stringify({ schemaVersion: "1.0", packageId: "fac-package-test", kind: "bad", geographicScope: "", files: [] }));
    await expect(readSignedManifest(path)).rejects.toThrow("kind");
  });
  it("requires an explicit as-of timestamp in the offline verification CLI", async () => {
    expect(() => requiredVerificationAsOf({})).toThrow("SMS_EVIDENCE_VERIFY_AS_OF is required");
    expect(requiredVerificationAsOf({ SMS_EVIDENCE_VERIFY_AS_OF: "2026-08-09T00:00:00Z" })).toBe("2026-08-09T00:00:00Z");
  });
  it("does not provide implicit private-key discovery", () => { expect(() => explicitPrivateKey(undefined)).toThrow("explicitly"); });
});
