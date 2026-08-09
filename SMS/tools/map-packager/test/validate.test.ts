import { generateKeyPairSync } from "node:crypto";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { verifyGeoPackage } from "@fac-isr/geo";
import {
  buildGeoPackageManifest,
  signGeoPackageManifest,
} from "../src/validate.js";

const pair = generateKeyPairSync("ed25519");
const privateKey = pair.privateKey.export({ type: "pkcs8", format: "pem" }).toString();
const publicKey = pair.publicKey.export({ type: "spki", format: "pem" }).toString();
const paths: string[] = [];

afterEach(async () => {
  await Promise.all(paths.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

const metadata = {
  schemaVersion: "1.0" as const,
  packageId: "fac-map-staging",
  kind: "map" as const,
  issuer: "FAC staging",
  version: "1.0.0",
  issuedAtUtc: "2026-08-08T00:00:00Z",
  effectiveFromUtc: "2026-08-08T00:00:00Z",
  expiresAtUtc: "2027-08-08T00:00:00Z",
  geographicScope: "Colombia",
  keyId: "fixture-ed25519",
  dependencies: [],
  qualification: "approved" as const,
  caveats: ["synthetic fixture; not operational aeronautical data"],
  format: "pmtiles" as const,
  horizontalDatum: "EPSG:4326",
  layers: [{
    id: "open-context",
    title: "Open context",
    authority: "OpenStreetMap contributors",
    authorityClass: "open-context" as const,
    effectiveFromUtc: "2026-08-08T00:00:00Z",
    extent: [-79, -5, -66, 13] as [number, number, number, number],
    horizontalDatum: "EPSG:4326",
    contentSha256: "a".repeat(64),
  }],
};

describe("map package staging validation", () => {
  it("builds a deterministic inventory, signs it, and verifies offline", async () => {
    const directory = await mkdtemp(join(tmpdir(), "fac-map-staging-"));
    paths.push(directory);
    await mkdir(join(directory, "tiles"));
    await writeFile(join(directory, "tiles", "z.pmtiles"), "z\n");
    await writeFile(join(directory, "a.json"), "{}\n");
    await writeFile(join(directory, "evidence-package-manifest.json"), "control\n");

    const unsigned = await buildGeoPackageManifest(directory, metadata);
    expect(unsigned.files.map((file) => file.path)).toEqual(["a.json", "tiles/z.pmtiles"]);
    const signed = signGeoPackageManifest(unsigned, privateKey);
    const report = await verifyGeoPackage(directory, signed, publicKey, { asOfUtc: "2026-08-09T00:00:00Z" });
    expect(report.ok).toBe(true);
  });

  it("keeps an incomplete staging directory invalid", async () => {
    const directory = await mkdtemp(join(tmpdir(), "fac-map-staging-"));
    paths.push(directory);
    await writeFile(join(directory, "a.json"), "{}\n");
    const unsigned = await buildGeoPackageManifest(directory, metadata);
    const signed = signGeoPackageManifest(unsigned, privateKey);
    await rm(join(directory, "a.json"));
    const report = await verifyGeoPackage(directory, signed, publicKey, { asOfUtc: "2026-08-09T00:00:00Z" });
    expect(report.ok).toBe(false);
    expect(report.checks).toContainEqual(expect.objectContaining({ id: "file-set", status: "fail" }));
  });
});
