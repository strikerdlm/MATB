import { generateKeyPairSync } from "node:crypto";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { manifestContentDigest, sha256File, signManifest } from "@fac-isr/evidence";
import {
  parseGeoPackageManifest,
  rejectStaleOrDowngradedPackage,
  verifyGeoPackage,
} from "../src/index.js";
import type { GeoPackageManifest } from "../src/index.js";

const keys = generateKeyPairSync("ed25519");
const privateKey = keys.privateKey.export({ type: "pkcs8", format: "pem" }).toString();
const publicKey = keys.publicKey.export({ type: "spki", format: "pem" }).toString();
const directories: string[] = [];
const hash = "a".repeat(64);

afterEach(async () => {
  await Promise.all(directories.splice(0).map((directory) => rm(directory, { recursive: true, force: true })));
});

async function fixture(): Promise<{ directory: string; manifest: GeoPackageManifest }> {
  const directory = await mkdtemp(join(tmpdir(), "fac-geo-package-"));
  directories.push(directory);
  await mkdir(join(directory, "tiles"));
  await writeFile(join(directory, "tiles", "base.pmtiles"), "synthetic pmtiles fixture\n");
  const path = join(directory, "tiles", "base.pmtiles");
  const file = { path: "tiles/base.pmtiles", sha256: await sha256File(path), sizeBytes: 26 };
  const unsigned = {
    schemaVersion: "1.0" as const,
    packageId: "fac-geo-context",
    kind: "map" as const,
    issuer: "FAC geospatial staging",
    version: "1.0.0",
    issuedAtUtc: "2026-08-08T00:00:00Z",
    effectiveFromUtc: "2026-08-08T00:00:00Z",
    expiresAtUtc: "2027-08-08T00:00:00Z",
    geographicScope: "Colombia",
    contentSha256: manifestContentDigest([file]),
    signature: "",
    keyId: "fixture-ed25519",
    dependencies: [],
    files: [file],
    qualification: "approved" as const,
    caveats: ["synthetic fixture; not operational aeronautical data"],
    format: "pmtiles" as const,
    horizontalDatum: "EPSG:4326",
    layers: [{
      id: "osm-context",
      title: "Open context",
      authority: "OpenStreetMap contributors",
      authorityClass: "open-context" as const,
      effectiveFromUtc: "2026-08-08T00:00:00Z",
      expiresAtUtc: "2027-08-08T00:00:00Z",
      extent: [-79, -5, -66, 13] as [number, number, number, number],
      horizontalDatum: "EPSG:4326",
      contentSha256: hash,
    }],
  };
  return { directory, manifest: parseGeoPackageManifest(signManifest(unsigned, privateKey)) };
}

function asOf() {
  return { asOfUtc: "2026-08-09T00:00:00Z" };
}

describe("signed offline geospatial package verification", () => {
  it("accepts an intact, signed package with approved geometry metadata", async () => {
    const { directory, manifest } = await fixture();
    const report = await verifyGeoPackage(directory, manifest, publicKey, asOf());
    expect(report.ok).toBe(true);
    expect(report.checks).toContainEqual(expect.objectContaining({ id: "geo-metadata", status: "pass" }));
  });

  it.each([
    ["tampered content", async () => {
      const candidate = await fixture();
      await writeFile(join(candidate.directory, "tiles", "base.pmtiles"), "tampered\n");
      return candidate;
    }],
    ["unsigned manifest", async () => {
      const candidate = await fixture();
      return { ...candidate, manifest: { ...candidate.manifest, signature: "" } as GeoPackageManifest };
    }],
    ["expired package", async () => {
      const candidate = await fixture();
      return { ...candidate, manifest: { ...candidate.manifest, expiresAtUtc: "2026-08-08T00:00:00Z" } };
    }],
    ["unsupported datum", async () => {
      const candidate = await fixture();
      const changed = { ...candidate.manifest, horizontalDatum: "EPSG:3857", signature: "" };
      return { ...candidate, manifest: parseGeoPackageManifest(signManifest(changed, privateKey)) };
    }],
  ])("rejects %s", async (_label, candidateFactory) => {
    const candidate = await candidateFactory();
    const report = await verifyGeoPackage(candidate.directory, candidate.manifest, publicKey, asOf());
    expect(report.ok).toBe(false);
  });

  it("rejects a package with an unavailable dependency", async () => {
    const candidate = await fixture();
    const dependency = { packageId: "fac-base-map", version: "1.0.0", contentSha256: hash };
    const manifest = parseGeoPackageManifest(signManifest({ ...candidate.manifest, dependencies: [dependency], signature: "" }, privateKey));
    const report = await verifyGeoPackage(candidate.directory, manifest, publicKey, asOf());
    expect(report.ok).toBe(false);
    expect(report.checks).toContainEqual(expect.objectContaining({ id: "dependencies", status: "fail" }));
  });

  it("rejects stale or downgraded replacements before activation", async () => {
    const { manifest } = await fixture();
    expect(() => rejectStaleOrDowngradedPackage(manifest, { ...manifest, version: "0.9.0" }, "2026-08-09T00:00:00Z")).toThrow(/downgrade/i);
    expect(() => rejectStaleOrDowngradedPackage(manifest, { ...manifest, version: "2.0.0", expiresAtUtc: "2026-08-08T01:00:00Z" }, "2026-08-09T00:00:00Z")).toThrow(/stale|expired/i);
  });
});
