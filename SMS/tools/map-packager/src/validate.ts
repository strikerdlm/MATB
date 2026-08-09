import { lstat, readdir, readFile, stat, writeFile } from "node:fs/promises";
import { relative, resolve, sep } from "node:path";
import {
  manifestContentDigest,
  sha256File,
  signManifest,
} from "@fac-isr/evidence";
import type { ManifestFile } from "@fac-isr/evidence";
import {
  parseGeoPackageManifest,
  verifyGeoPackage,
} from "@fac-isr/geo";
import type {
  GeoPackageManifest,
  GeoPackageVerificationOptions,
} from "@fac-isr/geo";
import type { VerificationReport } from "@fac-isr/evidence";

const CONTROL_FILES = new Set([
  "evidence-package-manifest.json",
  "evidence-package-manifest.sig",
  "evidence-package-public-key.pem",
]);

export type GeoPackageManifestMetadata = Omit<GeoPackageManifest, "files" | "contentSha256" | "signature">;

export interface GeoPackageManifestDraft extends GeoPackageManifestMetadata {
  files: ManifestFile[];
  contentSha256: string;
  signature: "";
}

async function collectFiles(root: string, current = root): Promise<string[]> {
  const entries = await readdir(current, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const full = resolve(current, entry.name);
    const relativePath = relative(root, full).split(sep).join("/");
    if (entry.isSymbolicLink()) throw new Error(`symbolic links are not permitted: ${relativePath}`);
    if (entry.isDirectory()) files.push(...await collectFiles(root, full));
    else if (entry.isFile() && !CONTROL_FILES.has(relativePath)) files.push(relativePath);
    else if (!entry.isFile()) throw new Error(`unsupported package entry: ${relativePath}`);
  }
  return files.sort();
}

/** Build a stable unsigned manifest draft from a closed staging directory. */
export async function buildGeoPackageManifest(
  directory: string,
  metadata: GeoPackageManifestMetadata,
): Promise<GeoPackageManifestDraft> {
  const root = resolve(directory);
  const info = await lstat(root);
  if (!info.isDirectory() || info.isSymbolicLink()) throw new Error("package directory must be a regular directory");
  const paths = await collectFiles(root);
  if (paths.length === 0) throw new Error("package directory must contain at least one payload file");
  const files: ManifestFile[] = [];
  for (const path of paths) {
    const full = resolve(root, path);
    const fileInfo = await stat(full);
    if (!fileInfo.isFile()) throw new Error(`package payload is not a regular file: ${path}`);
    files.push({ path, sha256: await sha256File(full), sizeBytes: fileInfo.size });
  }
  const draft: GeoPackageManifestDraft = {
    ...metadata,
    files,
    contentSha256: manifestContentDigest(files),
    signature: "",
  };
  // Validate all geo-specific metadata before a private key is used. A dummy
  // syntactically valid signature is never written or returned as signed data.
  parseGeoPackageManifest({ ...draft, signature: "A" });
  return draft;
}

/** Sign a previously inventoried draft using explicit staging-only key material. */
export function signGeoPackageManifest(
  draft: GeoPackageManifestDraft,
  privateKey: string | Buffer,
): GeoPackageManifest {
  const signed = signManifest({ ...draft, signature: "" }, privateKey);
  return parseGeoPackageManifest(signed);
}

export async function readGeoPackageManifest(path: string): Promise<GeoPackageManifest> {
  return parseGeoPackageManifest(JSON.parse(await readFile(path, "utf8")) as unknown);
}

export async function writeGeoPackageManifest(directory: string, manifest: GeoPackageManifest): Promise<void> {
  await writeFile(resolve(directory, "evidence-package-manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  await writeFile(resolve(directory, "evidence-package-manifest.sig"), `${manifest.signature}\n`, "utf8");
}

export function validateMapPackage(
  directory: string,
  manifest: unknown,
  publicKey: string | Buffer,
  options: GeoPackageVerificationOptions = {},
): Promise<VerificationReport> {
  return verifyGeoPackage(directory, manifest, publicKey, options);
}
