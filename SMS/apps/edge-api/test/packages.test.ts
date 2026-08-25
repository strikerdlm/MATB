import { createHash, generateKeyPairSync } from "node:crypto";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { basename, join } from "node:path";
import { tmpdir } from "node:os";
import { afterEach, describe, expect, it } from "vitest";
import { manifestContentDigest, signManifest, type SignedPackageManifest } from "@fac-isr/evidence";
import type { EdgeServer } from "../src/server.js";
import { authenticatedTestServer } from "./http-test-auth.js";

const asOfUtc = "2026-08-09T18:00:00.000Z";

function signedPackage(root: string, version: string): { directory: string; manifest: SignedPackageManifest; publicKeyPem: string } {
  const directoryPath = join(root, `map-${version.replaceAll(".", "-")}`);
  mkdirSync(directoryPath);
  const content = Buffer.from(`map package ${version}`, "utf8");
  writeFileSync(join(directoryPath, "map.txt"), content);
  const files = [{ path: "map.txt", sha256: createHash("sha256").update(content).digest("hex"), sizeBytes: content.byteLength }];
  const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
  const manifest = signManifest({
    schemaVersion: "1.0",
    packageId: "map-colombia",
    kind: "map",
    issuer: "fac-isr",
    version,
    issuedAtUtc: "2026-08-09T17:00:00.000Z",
    effectiveFromUtc: "2026-08-09T17:30:00.000Z",
    expiresAtUtc: "2027-08-09T17:30:00.000Z",
    geographicScope: "Colombia",
    contentSha256: manifestContentDigest(files),
    keyId: "local-key-1",
    dependencies: [],
    files,
    qualification: "approved",
    caveats: ["local fixture"],
    signature: "",
  }, privateKey.export({ type: "pkcs1", format: "pem" }).toString());
  return { directory: basename(directoryPath), manifest, publicKeyPem: publicKey.export({ type: "spki", format: "pem" }).toString() };
}

describe("signed package import and quarantine", () => {
  let app: EdgeServer | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("quarantines an unsigned package before activation", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-packages-"));
    const server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled", packageDirectory: root });
    app = server.app;
    const response = await server.request({ method: "POST", url: "/api/packages/import", payload: { directory: ".", manifest: { schemaVersion: "1.0", packageId: "map-colombia", kind: "map", version: "1.0.0" }, asOfUtc } });

    expect(response.statusCode).toBe(422);
    expect(response.json()).toMatchObject({ state: "quarantined", packageId: "map-colombia" });
  });

  it("refuses a signed downgrade while preserving the quarantine record", async () => {
    const root = mkdtempSync(join(tmpdir(), "fac-isr-packages-"));
    const server = await authenticatedTestServer({ databaseUrl: ":memory:", internet: "disabled", packageDirectory: root });
    app = server.app;
    const current = signedPackage(root, "1.2.0");
    const first = await server.request({ method: "POST", url: "/api/packages/import", payload: { ...current, asOfUtc } });
    expect(first.statusCode).toBe(201);
    expect(first.json()).toMatchObject({ state: "active", packageId: "map-colombia", version: "1.2.0" });

    const older = signedPackage(root, "1.1.0");
    const downgrade = await server.request({ method: "POST", url: "/api/packages/import", payload: { ...older, asOfUtc } });
    expect(downgrade.statusCode).toBe(422);
    expect(downgrade.json()).toMatchObject({ state: "quarantined", reason: expect.stringMatching(/downgrade/i) });

    const quarantine = await server.request({ method: "GET", url: "/api/packages/quarantine" });
    expect(quarantine.statusCode).toBe(200);
    expect(quarantine.json().packages).toEqual(expect.arrayContaining([expect.objectContaining({ version: "1.1.0", state: "quarantined" })]));
  });
});
