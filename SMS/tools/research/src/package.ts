import { constants as fsConstants } from "node:fs";
import { createHash } from "node:crypto";
import { mkdir, open, readFile, lstat } from "node:fs/promises";
import { dirname, isAbsolute, parse, relative, resolve, sep } from "node:path";
import { assertSignedPackageManifest, canonicalJson, manifestContentDigest, signManifest } from "@fac-isr/evidence";
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

function pathsOverlap(left: string, right: string): boolean {
  const relation = relative(left, right);
  return relation === "" || (relation !== ".." && !relation.startsWith(`..${sep}`) && !isAbsolute(relation));
}

/** Reject a path whose existing components include a symlink. */
async function assertNoSymlinkComponents(path: string, field: string): Promise<void> {
  const absolute = resolve(path);
  const root = parse(absolute).root;
  const segments = absolute.slice(root.length).split(sep).filter(Boolean);
  let current = root;
  for (const segment of segments) {
    current = resolve(current, segment);
    let info;
    try { info = await lstat(current); } catch (error) {
      throw new Error(`${field} component is unavailable: ${current} (${error instanceof Error ? error.message : String(error)})`);
    }
    if (info.isSymbolicLink()) throw new Error(`${field} may not contain symbolic links: ${current}`);
  }
}

function sameFile(left: Awaited<ReturnType<typeof lstat>>, right: Awaited<ReturnType<typeof lstat>>): boolean {
  return left.dev === right.dev && left.ino === right.ino && left.size === right.size && left.mode === right.mode;
}

function sha256Contents(contents: Buffer): string {
  return createHash("sha256").update(contents).digest("hex");
}

/** Read a source only after checking its parents and final component without following symlinks. */
async function readSafeSource(source: string, label: string): Promise<Buffer> {
  await assertNoSymlinkComponents(dirname(source), `${label} parent`);
  const before = await lstat(source);
  if (before.isSymbolicLink() || !before.isFile()) throw new Error(`package source is not a regular non-symlink file: ${label}`);
  const handle = await open(source, fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW);
  try {
    const opened = await handle.stat();
    if (!sameFile(before, opened)) throw new Error(`package source changed while opening: ${label}`);
    const contents = await handle.readFile();
    const after = await handle.stat();
    if (!sameFile(opened, after)) throw new Error(`package source changed while reading: ${label}`);
    return contents;
  } finally {
    await handle.close();
  }
}

async function writeSafeDestination(outputDirectory: string, destinationPath: string, contents: Buffer): Promise<void> {
  const destination = contained(outputDirectory, destinationPath, "packagePath");
  const parent = dirname(destination);
  await mkdir(parent, { recursive: true });
  await assertNoSymlinkComponents(parent, "package output parent");
  const handle = await open(destination, fsConstants.O_WRONLY | fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_NOFOLLOW, 0o600);
  try { await handle.writeFile(contents); } finally { await handle.close(); }
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
  if (pathsOverlap(sourceRoot, outputDirectory) || pathsOverlap(outputDirectory, sourceRoot)) throw new Error("outputDirectory must not equal, contain, or be contained by sourceRoot");
  try { await lstat(outputDirectory); throw new Error("outputDirectory already exists; refusing to erase caller-selected output"); } catch (error) {
    if (!(error instanceof Error) || !/ENOENT/.test(String((error as NodeJS.ErrnoException).code))) throw error;
  }
  await assertNoSymlinkComponents(sourceRoot, "sourceRoot");
  const sourceRootInfo = await lstat(sourceRoot);
  if (!sourceRootInfo.isDirectory()) throw new Error("sourceRoot must be a directory");
  await assertNoSymlinkComponents(dirname(outputDirectory), "outputDirectory parent");

  const staged: Array<{ path: string; contents: Buffer }> = [];
  const paths = new Set<string>();
  for (const file of input.files) {
    const destinationPath = packagePath(file);
    if (paths.has(destinationPath)) throw new Error(`duplicate package path: ${destinationPath}`);
    paths.add(destinationPath);
    const source = contained(sourceRoot, file.sourcePath, "sourcePath");
    staged.push({ path: destinationPath, contents: await readSafeSource(source, file.sourcePath) });
  }
  const inventory: ManifestFile[] = staged.map((file) => ({ path: file.path, sha256: sha256Contents(file.contents), sizeBytes: file.contents.length }));
  inventory.sort((left, right) => left.path < right.path ? -1 : left.path > right.path ? 1 : 0);
  const signed = signManifest({ ...input.manifest, files: inventory, contentSha256: manifestContentDigest(inventory) }, input.privateKey);
  // All caller input, source bytes, and signing material have now been checked. Only then create output.
  await mkdir(outputDirectory, { recursive: false, mode: 0o700 });
  await assertNoSymlinkComponents(outputDirectory, "outputDirectory");
  for (const file of staged) await writeSafeDestination(outputDirectory, file.path, file.contents);
  await writeSafeDestination(outputDirectory, "evidence-package-manifest.json", Buffer.from(`${canonicalJson(signed)}\n`, "utf8"));
  await writeSafeDestination(outputDirectory, "evidence-package-manifest.sig", Buffer.from(`${signed.signature}\n`, "utf8"));
  return signed;
}

export async function readSignedManifest(path: string): Promise<SignedPackageManifest> {
  const parsed: unknown = JSON.parse(await readFile(path, "utf8"));
  assertSignedPackageManifest(parsed);
  return parsed;
}

/** A lightweight assertion used by command handlers before accepting a supplied PEM value. */
export function explicitPrivateKey(value: string | undefined): string {
  if (value === undefined || value.trim() === "") throw new Error("private key material must be supplied explicitly by staging input or SMS_EVIDENCE_PRIVATE_KEY");
  if (!value.includes("PRIVATE KEY")) throw new Error("private key material is not PEM private-key data");
  return value;
}

export function isSha256(value: string): boolean { return SHA256.test(value); }
