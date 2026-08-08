import { mkdir, readFile, rm, stat, writeFile, copyFile } from "node:fs/promises";
import { dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { canonicalJson, manifestContentDigest, signManifest, sha256File } from "@fac-isr/evidence";
import type { ManifestFile, SignedPackageManifest } from "@fac-isr/evidence";

const SHA256 = /^[a-f0-9]{64}$/;

export interface PackageSourceFile {
  /** Relative to sourceRoot; never accepted as an absolute or traversing path. */
  sourcePath: string;
  /** Relative destination inside the closed package directory. */
  packagePath?: string;
}

export interface AssemblePackageInput {
  sourceRoot: string;
  outputDirectory: string;
  files: readonly PackageSourceFile[];
  manifest: Omit<SignedPackageManifest, "files" | "contentSha256" | "signature">;
  /** Explicit staging-only material. This helper never discovers or loads a private key. */
  privateKey: string | Buffer;
}

function contained(root: string, candidate: string, field: string): string {
  if (!candidate || isAbsolute(candidate) || candidate.includes("\\")) throw new Error(`${field} must be a non-empty relative POSIX path`);
  const target = resolve(root, candidate);
  const fromRoot = relative(root, target);
  if (fromRoot === "" || fromRoot === ".." || fromRoot.startsWith(`..${sep}`) || isAbsolute(fromRoot)) throw new Error(`${field} escapes its root`);
  return target;
}

function packagePath(input: PackageSourceFile): string {
  const output = input.packagePath ?? input.sourcePath;
  if (output.split("/").some((part) => !part || part === "." || part === "..")) throw new Error("packagePath contains traversal");
  return output;
}

/**
 * Create a closed package directory with a sorted file inventory and Ed25519 signature.
 * Callers must provide private key material explicitly from an approved staging secret;
 * this module neither reads environment variables nor searches the repository for keys.
 */
export async function assembleEvidencePackage(input: AssemblePackageInput): Promise<SignedPackageManifest> {
  const sourceRoot = resolve(input.sourceRoot);
  const outputDirectory = resolve(input.outputDirectory);
  if (!Array.isArray(input.files) || input.files.length === 0) throw new Error("package must contain at least one file");
  await rm(outputDirectory, { recursive: true, force: true });
  await mkdir(outputDirectory, { recursive: true });
  const inventory: ManifestFile[] = [];
  const paths = new Set<string>();
  for (const file of input.files) {
    const destinationPath = packagePath(file);
    if (paths.has(destinationPath)) throw new Error(`duplicate package path: ${destinationPath}`);
    paths.add(destinationPath);
    const source = contained(sourceRoot, file.sourcePath, "sourcePath");
    const destination = contained(outputDirectory, destinationPath, "packagePath");
    const info = await stat(source);
    if (!info.isFile()) throw new Error(`package source is not a file: ${file.sourcePath}`);
    await mkdir(dirname(destination), { recursive: true });
    await copyFile(source, destination, 0);
    inventory.push({ path: destinationPath, sha256: await sha256File(destination), sizeBytes: info.size });
  }
  inventory.sort((left, right) => left.path < right.path ? -1 : left.path > right.path ? 1 : 0);
  const signed = signManifest({ ...input.manifest, files: inventory, contentSha256: manifestContentDigest(inventory) }, input.privateKey);
  await writeFile(resolve(outputDirectory, "evidence-package-manifest.json"), `${canonicalJson(signed)}\n`, "utf8");
  await writeFile(resolve(outputDirectory, "evidence-package-manifest.sig"), `${signed.signature}\n`, "utf8");
  return signed;
}

export async function readSignedManifest(path: string): Promise<SignedPackageManifest> {
  const parsed: unknown = JSON.parse(await readFile(path, "utf8"));
  if (parsed === null || typeof parsed !== "object") throw new Error("manifest file must contain an object");
  return parsed as SignedPackageManifest;
}

/** A lightweight assertion used by command handlers before accepting a supplied PEM value. */
export function explicitPrivateKey(value: string | undefined): string {
  if (value === undefined || value.trim() === "") throw new Error("private key material must be supplied explicitly by staging input or SMS_EVIDENCE_PRIVATE_KEY");
  if (!value.includes("PRIVATE KEY")) throw new Error("private key material is not PEM private-key data");
  return value;
}

export function isSha256(value: string): boolean { return SHA256.test(value); }
