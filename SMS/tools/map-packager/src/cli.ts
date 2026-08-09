import { readFile, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { buildGeoPackageManifest, readGeoPackageManifest, signGeoPackageManifest, writeGeoPackageManifest } from "./validate.js";
import type { GeoPackageManifestMetadata, GeoPackageManifestDraft } from "./validate.js";
import { verifyGeoPackage } from "@fac-isr/geo";

function argument(name: string): string | undefined {
  const index = process.argv.indexOf(`--${name}`);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

function requiredArgument(name: string): string {
  const value = argument(name);
  if (value === undefined || value.trim() === "") throw new Error(`--${name} is required`);
  return value;
}

async function jsonFile(path: string): Promise<unknown> {
  return JSON.parse(await readFile(resolve(path), "utf8")) as unknown;
}

function metadataOnly(value: unknown): GeoPackageManifestMetadata {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error("metadata must be a JSON object");
  const { files: _files, contentSha256: _contentSha256, signature: _signature, ...metadata } = value as Record<string, unknown>;
  return metadata as GeoPackageManifestMetadata;
}

async function main(): Promise<void> {
  const command = process.argv[2];
  if (command === "inspect") {
    const directory = resolve(requiredArgument("directory"));
    const manifestPath = argument("manifest") ?? join(directory, "evidence-package-manifest.json");
    process.stdout.write(`${JSON.stringify(await readGeoPackageManifest(manifestPath), null, 2)}\n`);
    return;
  }
  if (command === "build-manifest") {
    const directory = resolve(requiredArgument("directory"));
    const metadata = metadataOnly(await jsonFile(requiredArgument("metadata")));
    const draft = await buildGeoPackageManifest(directory, metadata);
    const output = resolve(argument("output") ?? join(directory, "evidence-package-manifest.json"));
    await writeFile(output, `${JSON.stringify(draft, null, 2)}\n`, "utf8");
    process.stdout.write(`${output}\n`);
    return;
  }
  if (command === "sign") {
    const directory = resolve(requiredArgument("directory"));
    const manifestPath = resolve(argument("manifest") ?? join(directory, "evidence-package-manifest.json"));
    const draft = JSON.parse(await readFile(manifestPath, "utf8")) as GeoPackageManifestDraft;
    const privateKeyPath = resolve(requiredArgument("private-key"));
    const privateKey = await readFile(privateKeyPath);
    const signed = signGeoPackageManifest(draft, privateKey);
    await writeGeoPackageManifest(directory, signed);
    process.stdout.write(`${JSON.stringify(signed, null, 2)}\n`);
    return;
  }
  if (command === "verify") {
    const directory = resolve(requiredArgument("directory"));
    const manifest = await readGeoPackageManifest(argument("manifest") ?? join(directory, "evidence-package-manifest.json"));
    const publicKey = await readFile(resolve(requiredArgument("public-key")));
    const report = await verifyGeoPackage(directory, manifest, publicKey, { asOfUtc: requiredArgument("as-of") });
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
    if (!report.ok) process.exitCode = 1;
    return;
  }
  throw new Error("usage: map-packager <inspect|build-manifest|sign|verify> [options]");
}

export { main };

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error: unknown) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
