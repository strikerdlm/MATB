import { generateKeyPairSync } from "node:crypto";
import { chmod, lstat, mkdir, mkdtemp, readFile, readdir, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";
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
    const root = await mkdtemp(join(tmpdir(), "fac-evidence-source-")); const outputParent = await mkdtemp(join(tmpdir(), "fac-evidence-output-")); const output = join(outputParent, "package"); paths.push(root, outputParent); await mkdir(output);
    await writeFile(join(root, "rule.json"), "{}\n"); await writeFile(join(output, "preserve.txt"), "do-not-delete");
    await expect(assembleEvidencePackage({ sourceRoot: root, outputDirectory: output, files: [{ sourcePath: "rule.json" }], privateKey, manifest: { schemaVersion: "1.0", packageId: "fac-package-test", kind: "regulatory", issuer: "test issuer", version: "1.0.0", issuedAtUtc: "2026-08-08T00:00:00Z", effectiveFromUtc: "2026-08-08T00:00:00Z", geographicScope: "Colombia", keyId: "test", dependencies: [], qualification: "qualified-review", caveats: ["test only"] } })).rejects.toThrow("already exists");
    await expect(readFile(join(output, "preserve.txt"), "utf8")).resolves.toBe("do-not-delete");
  });
  it("rejects a group/other-writable publish parent before creating staging", async () => {
    const root = await mkdtemp(join(tmpdir(), "fac-evidence-source-")); const outputParent = await mkdtemp(join(tmpdir(), "fac-evidence-output-")); const output = join(outputParent, "package"); paths.push(root, outputParent);
    await writeFile(join(root, "rule.json"), "{}\n"); await chmod(outputParent, 0o777);
    await expect(assembleEvidencePackage({ sourceRoot: root, outputDirectory: output, files: [{ sourcePath: "rule.json" }], privateKey, manifest: { schemaVersion: "1.0", packageId: "fac-package-test", kind: "regulatory", issuer: "test issuer", version: "1.0.0", issuedAtUtc: "2026-08-08T00:00:00Z", effectiveFromUtc: "2026-08-08T00:00:00Z", geographicScope: "Colombia", keyId: "test", dependencies: [], qualification: "qualified-review", caveats: ["test only"] } })).rejects.toThrow("outputDirectory parent");
    expect((await readdir(outputParent)).filter((name) => name.startsWith(`.${basename(output)}.staging-`))).toEqual([]);
  });
  it.each([
    ["NUL", "bad\0name.txt"],
    ["backslash", "bad\\name.txt"],
    ["oversized component", "x".repeat(256)],
    ["oversized path", Array.from({ length: 17 }, () => "x".repeat(255)).join("/")],
  ])("rejects a destination with %s before creating staging", async (_label, packagePath) => {
    const root = await mkdtemp(join(tmpdir(), "fac-evidence-source-")); const outputParent = await mkdtemp(join(tmpdir(), "fac-evidence-output-")); const output = join(outputParent, "package"); paths.push(root, outputParent);
    await writeFile(join(root, "rule.json"), "{}\n");
    await expect(assembleEvidencePackage({ sourceRoot: root, outputDirectory: output, files: [{ sourcePath: "rule.json", packagePath }], privateKey, manifest: { schemaVersion: "1.0", packageId: "fac-package-test", kind: "regulatory", issuer: "test issuer", version: "1.0.0", issuedAtUtc: "2026-08-08T00:00:00Z", effectiveFromUtc: "2026-08-08T00:00:00Z", geographicScope: "Colombia", keyId: "test", dependencies: [], qualification: "qualified-review", caveats: ["test only"] } })).rejects.toThrow("packagePath");
    await expect(lstat(output)).rejects.toMatchObject({ code: "ENOENT" });
    expect((await readdir(outputParent)).filter((name) => name.startsWith(`.${basename(output)}.staging-`))).toEqual([]);
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
  it("preflights file/directory prefix collisions and reserved control paths", async () => {
    const root = await mkdtemp(join(tmpdir(), "fac-evidence-collision-source-")); const outputParent = await mkdtemp(join(tmpdir(), "fac-evidence-collision-output-")); const output = join(outputParent, "package"); paths.push(root, outputParent);
    await writeFile(join(root, "one.txt"), "one\n"); await writeFile(join(root, "two.txt"), "two\n");
    const base = { sourceRoot: root, outputDirectory: output, privateKey, manifest: { schemaVersion: "1.0" as const, packageId: "fac-package-test", kind: "regulatory" as const, issuer: "test issuer", version: "1.0.0", issuedAtUtc: "2026-08-08T00:00:00Z", effectiveFromUtc: "2026-08-08T00:00:00Z", geographicScope: "Colombia", keyId: "test", dependencies: [], qualification: "qualified-review" as const, caveats: ["test only"] } };
    await expect(assembleEvidencePackage({ ...base, files: [{ sourcePath: "one.txt", packagePath: "foo" }, { sourcePath: "two.txt", packagePath: "foo/bar" }] })).rejects.toThrow("prefix collision");
    await expect(lstat(output)).rejects.toMatchObject({ code: "ENOENT" });
    await expect(assembleEvidencePackage({ ...base, files: [{ sourcePath: "one.txt", packagePath: "evidence-package-manifest.json" }] })).rejects.toThrow("reserved");
    await expect(lstat(output)).rejects.toMatchObject({ code: "ENOENT" });
  });
  it("cleans a partially written private staging package after a destination failure", async () => {
    const root = await mkdtemp(join(tmpdir(), "fac-evidence-atomic-source-")); const outputParent = await mkdtemp(join(tmpdir(), "fac-evidence-atomic-output-")); const output = join(outputParent, "package"); paths.push(root, outputParent);
    await writeFile(join(root, "good.txt"), "good\n"); await writeFile(join(root, "bad.txt"), "bad\n");
    const tooLong = "x".repeat(256);
    await expect(assembleEvidencePackage({ sourceRoot: root, outputDirectory: output, files: [{ sourcePath: "good.txt", packagePath: "content/good.txt" }, { sourcePath: "bad.txt", packagePath: tooLong }], privateKey, manifest: { schemaVersion: "1.0", packageId: "fac-package-test", kind: "regulatory", issuer: "test issuer", version: "1.0.0", issuedAtUtc: "2026-08-08T00:00:00Z", effectiveFromUtc: "2026-08-08T00:00:00Z", geographicScope: "Colombia", keyId: "test", dependencies: [], qualification: "qualified-review", caveats: ["test only"] } })).rejects.toThrow();
    await expect(lstat(output)).rejects.toMatchObject({ code: "ENOENT" });
    expect((await readdir(outputParent)).filter((name) => name.startsWith(`.${basename(output)}.staging-`))).toEqual([]);
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
