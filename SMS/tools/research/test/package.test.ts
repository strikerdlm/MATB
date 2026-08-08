import { generateKeyPairSync } from "node:crypto";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { verifyPackage } from "@fac-isr/evidence";
import { assembleEvidencePackage, explicitPrivateKey, readSignedManifest } from "../src/package.js";

const paths: string[] = [];
const pair = generateKeyPairSync("ed25519");
const privateKey = pair.privateKey.export({ type: "pkcs8", format: "pem" }).toString();
const publicKey = pair.publicKey.export({ type: "spki", format: "pem" }).toString();
afterEach(async () => { await Promise.all(paths.splice(0).map((path) => rm(path, { recursive: true, force: true }))); });

describe("deterministic evidence package assembly", () => {
  it("builds a closed signed package from explicit staging key material", async () => {
    const root = await mkdtemp(join(tmpdir(), "fac-evidence-source-")); const output = await mkdtemp(join(tmpdir(), "fac-evidence-output-")); paths.push(root, output);
    await writeFile(join(root, "rule.json"), "{\"rule\":true}\n");
    const manifest = await assembleEvidencePackage({ sourceRoot: root, outputDirectory: output, files: [{ sourcePath: "rule.json", packagePath: "content/rule.json" }], privateKey, manifest: { schemaVersion: "1.0", packageId: "fac-package-test", kind: "regulatory", issuer: "test issuer", version: "1.0.0", issuedAtUtc: "2026-08-08T00:00:00Z", effectiveFromUtc: "2026-08-08T00:00:00Z", expiresAtUtc: "2027-08-08T00:00:00Z", keyId: "test", dependencies: [], qualification: "qualified-review", caveats: ["test only"] } });
    expect(await readSignedManifest(join(output, "evidence-package-manifest.json"))).toEqual(manifest);
    expect((await verifyPackage(output, manifest, publicKey, "2026-08-09T00:00:00Z")).ok).toBe(true);
    expect((await readFile(join(output, "evidence-package-manifest.sig"), "utf8")).trim()).toBe(manifest.signature);
  });
  it("does not provide implicit private-key discovery", () => { expect(() => explicitPrivateKey(undefined)).toThrow("explicitly"); });
});
