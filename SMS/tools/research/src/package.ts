import { constants as fsConstants } from "node:fs";
import { createHash } from "node:crypto";
import { lstat, mkdir, mkdtemp, open, readFile, rename, rm } from "node:fs/promises";
import type { FileHandle } from "node:fs/promises";
import { basename, dirname, isAbsolute, join, parse, relative, resolve, sep } from "node:path";
import { assertSignedPackageManifest, canonicalJson, manifestContentDigest, signManifest } from "@fac-isr/evidence";
import type { ManifestFile, SignedPackageManifest } from "@fac-isr/evidence";

const SHA256 = /^[a-f0-9]{64}$/;
const PACKAGE_CONTROL_FILES = new Set([
  "evidence-package-manifest.json",
  "evidence-package-manifest.sig",
  "evidence-package-public-key.pem",
]);
const MAX_PATH_BYTES = 4096;
const MAX_COMPONENT_BYTES = 255;
const DIRECTORY_FLAGS = fsConstants.O_RDONLY | fsConstants.O_DIRECTORY | fsConstants.O_NOFOLLOW;
const publishLocks = new Map<string, Promise<void>>();

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

/** Validate a package/source-relative path before it can reach path or fs APIs. */
function assertPortableRelativePath(value: unknown, field: string): asserts value is string {
  if (typeof value !== "string" || value.length === 0 || isAbsolute(value) || value.includes("\\") || value.includes("\0")) throw new Error(`${field} must be a non-empty relative POSIX path without backslash or NUL`);
  if (Buffer.byteLength(value, "utf8") > MAX_PATH_BYTES) throw new Error(`${field} exceeds ${MAX_PATH_BYTES} UTF-8 bytes`);
  const components = value.split("/");
  for (const component of components) {
    if (component === "" || component === "." || component === "..") throw new Error(`${field} has empty, dot, or dotdot component`);
    if (Buffer.byteLength(component, "utf8") > MAX_COMPONENT_BYTES) throw new Error(`${field} component exceeds ${MAX_COMPONENT_BYTES} UTF-8 bytes`);
    // Keep package paths portable to the Linux edge node and Windows staging
    // workstation; these characters are invalid or ambiguous on one of them.
    if (/[\u0000-\u001f\u007f<>:"|?*]/u.test(component) || /[. ]$/u.test(component)) throw new Error(`${field} contains a platform-invalid component`);
    if (/^(con|prn|aux|nul|clock\$|com[1-9]|lpt[1-9])(?:\..*)?$/iu.test(component)) throw new Error(`${field} contains a reserved platform name`);
  }
}

function contained(root: string, candidate: string, field: string): string {
  assertPortableRelativePath(candidate, field);
  const target = resolve(root, candidate);
  const fromRoot = relative(root, target);
  if (fromRoot === "" || fromRoot === ".." || fromRoot.startsWith(`..${sep}`) || isAbsolute(fromRoot)) throw new Error(`${field} escapes its root`);
  return target;
}

function packagePath(input: PackageSourceFile): string {
  const output = input.packagePath ?? input.sourcePath;
  assertPortableRelativePath(output, "packagePath");
  return output;
}

/** Reject exact reserved controls and file/directory prefix collisions. */
function assertDestinationPaths(paths: readonly string[]): void {
  for (const path of paths) {
    if (PACKAGE_CONTROL_FILES.has(path)) throw new Error(`packagePath is reserved: ${path}`);
  }
  const all = [...PACKAGE_CONTROL_FILES, ...paths].sort();
  for (let index = 1; index < all.length; index += 1) {
    const previous = all[index - 1];
    const current = all[index];
    if (previous === current) {
      if (PACKAGE_CONTROL_FILES.has(current)) throw new Error(`packagePath is reserved: ${current}`);
      throw new Error(`duplicate package path: ${current}`);
    }
    if (current.startsWith(`${previous}/`)) throw new Error(`package path prefix collision: ${previous} and ${current}`);
  }
}

function pathsOverlap(left: string, right: string): boolean {
  const relation = relative(left, right);
  return relation === "" || (relation !== ".." && !relation.startsWith(`..${sep}`) && !isAbsolute(relation));
}

function assertHostPath(value: string, field: string): void {
  if (value.includes("\0") || value.includes("\\") || Buffer.byteLength(value, "utf8") > MAX_PATH_BYTES) throw new Error(`${field} contains an invalid or overlong host path`);
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

function fdPath(handle: FileHandle): string {
  if (process.platform !== "linux") throw new Error("evidence package assembly requires Linux /proc directory-FD anchoring");
  return `/proc/self/fd/${handle.fd}`;
}

/** Require a directory that is private to this process's uid and writable by its owner. */
function assertTrustedDirectoryInfo(info: Awaited<ReturnType<typeof lstat>>, field: string): void {
  const uid = typeof process.getuid === "function" ? process.getuid() : undefined;
  const mode = Number(info.mode) & 0o777;
  if (uid === undefined || !info.isDirectory() || info.uid !== uid || (mode & 0o022) !== 0 || (mode & 0o200) === 0) {
    throw new Error(`${field} must be an existing directory owned by the process uid, owner-writable, and not group/other-writable`);
  }
}

/** Open every absolute path component with O_NOFOLLOW, retaining the final FD. */
async function openDirectoryPath(path: string, field: string): Promise<FileHandle> {
  const absolute = resolve(path);
  assertHostPath(absolute, field);
  const root = parse(absolute).root;
  let current = await open(root, DIRECTORY_FLAGS);
  try {
    const segments = absolute.slice(root.length).split(sep).filter(Boolean);
    for (const segment of segments) {
      const next = await open(join(fdPath(current), segment), DIRECTORY_FLAGS);
      await current.close();
      current = next;
    }
    return current;
  } catch (error) {
    await current.close();
    throw error;
  }
}

/** Require a real directory owned by this process's uid and not writable by group/other. */
async function openTrustedPublishParent(path: string): Promise<FileHandle> {
  const handle = await openDirectoryPath(path, "outputDirectory parent");
  try {
    const info = await handle.stat();
    assertTrustedDirectoryInfo(info, "outputDirectory parent");
  } catch (error) {
    await handle.close();
    throw error;
  }
  return handle;
}

/** Open/create one destination directory from an already-open directory FD. */
async function openChildDirectory(parent: FileHandle, component: string, field: string): Promise<FileHandle> {
  assertPortableRelativePath(component, field);
  const childPath = join(fdPath(parent), component);
  try {
    await mkdir(childPath, { recursive: false, mode: 0o700 });
  } catch (error) {
    if (!(error instanceof Error) || (error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
  }
  const child = await open(childPath, DIRECTORY_FLAGS);
  const info = await child.stat();
  try {
    assertTrustedDirectoryInfo(info, field);
  } catch (error) {
    await child.close();
    throw error;
  }
  return child;
}

/** Write using directory-FD anchoring so path checks cannot be bypassed by a symlink swap. */
async function writeSafeDestination(root: FileHandle, destinationPath: string, contents: Buffer): Promise<void> {
  assertPortableRelativePath(destinationPath, "packagePath");
  const components = destinationPath.split("/");
  const fileName = components.pop();
  if (fileName === undefined) throw new Error("packagePath must name a file");
  let current = root;
  const opened: FileHandle[] = [];
  try {
    for (const component of components) {
      current = await openChildDirectory(current, component, "package output parent");
      opened.push(current);
    }
    const destination = join(fdPath(current), fileName);
    const handle = await open(destination, fsConstants.O_WRONLY | fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_NOFOLLOW, 0o600);
    try { await handle.writeFile(contents); } finally { await handle.close(); }
  } finally {
    for (const handle of opened.reverse()) await handle.close();
  }
}

async function acquirePublishLock(key: string): Promise<() => void> {
  const predecessor = publishLocks.get(key) ?? Promise.resolve();
  let release!: () => void;
  const own = new Promise<void>((resolveOwn) => { release = resolveOwn; });
  const tail = predecessor.then(() => own);
  publishLocks.set(key, tail);
  await predecessor;
  return () => {
    release();
    if (publishLocks.get(key) === tail) publishLocks.delete(key);
  };
}

/**
 * Create a closed package directory with a sorted file inventory and Ed25519 signature.
 * Callers must provide private key material explicitly from an approved staging secret;
 * this module neither reads environment variables nor searches the repository for keys.
 */
export async function assembleEvidencePackage(input: AssemblePackageInput): Promise<SignedPackageManifest> {
  assertHostPath(input.sourceRoot, "sourceRoot");
  assertHostPath(input.outputDirectory, "outputDirectory");
  const sourceRoot = resolve(input.sourceRoot);
  const outputDirectory = resolve(input.outputDirectory);
  const outputName = basename(outputDirectory);
  if (outputName === "") throw new Error("outputDirectory must name a child of its parent directory");
  if (!Array.isArray(input.files) || input.files.length === 0) throw new Error("package must contain at least one file");
  if (pathsOverlap(sourceRoot, outputDirectory) || pathsOverlap(outputDirectory, sourceRoot)) throw new Error("outputDirectory must not equal, contain, or be contained by sourceRoot");
  await assertNoSymlinkComponents(sourceRoot, "sourceRoot");
  const sourceRootInfo = await lstat(sourceRoot);
  if (!sourceRootInfo.isDirectory()) throw new Error("sourceRoot must be a directory");

  // Resolve and validate every destination before reading sources or creating
  // any output. This catches exact collisions and file/directory prefixes,
  // including conflicts with the manifest/signature control paths.
  const planned = input.files.map((file) => ({
    path: packagePath(file),
    source: contained(sourceRoot, file.sourcePath, "sourcePath"),
    label: file.sourcePath,
  }));
  assertDestinationPaths(planned.map((file) => file.path));
  const staged: Array<{ path: string; contents: Buffer }> = [];
  for (const file of planned) staged.push({ path: file.path, contents: await readSafeSource(file.source, file.label) });
  const inventory: ManifestFile[] = staged.map((file) => ({ path: file.path, sha256: sha256Contents(file.contents), sizeBytes: file.contents.length }));
  inventory.sort((left, right) => left.path < right.path ? -1 : left.path > right.path ? 1 : 0);
  const signed = signManifest({ ...input.manifest, files: inventory, contentSha256: manifestContentDigest(inventory) }, input.privateKey);
  // Build privately, then publish with a same-parent rename. Only this
  // generated staging directory is ever removed on failure; caller output is
  // never recursively deleted or overwritten.
  const releasePublishLock = await acquirePublishLock(outputDirectory);
  let parentHandle: FileHandle | undefined;
  let stagingHandle: FileHandle | undefined;
  let stagingName: string | undefined;
  let stagingIdentity: Awaited<ReturnType<typeof lstat>> | undefined;
  let published = false;
  try {
    // Keep the trusted parent open from preflight through publish. Its private
    // ownership/mode boundary prevents an untrusted process from replacing
    // the directory between the destination check and the atomic rename.
    parentHandle = await openTrustedPublishParent(dirname(outputDirectory));
    const outputPath = join(fdPath(parentHandle), outputName);
    try { await lstat(outputPath); throw new Error("outputDirectory already exists; refusing to overwrite caller-selected output"); } catch (error) {
      if (!(error instanceof Error) || !/ENOENT/.test(String((error as NodeJS.ErrnoException).code))) throw error;
    }

    const stagingPath = await mkdtemp(join(fdPath(parentHandle), `.${outputName}.staging-`));
    stagingName = basename(stagingPath);
    stagingIdentity = await lstat(join(fdPath(parentHandle), stagingName));
    // Re-open and re-check the generated staging directory through the trusted
    // parent FD before writing anything into it.
    stagingHandle = await openChildDirectory(parentHandle, stagingName, "package staging directory");
    for (const file of staged) await writeSafeDestination(stagingHandle, file.path, file.contents);
    await writeSafeDestination(stagingHandle, "evidence-package-manifest.json", Buffer.from(`${canonicalJson(signed)}\n`, "utf8"));
    await writeSafeDestination(stagingHandle, "evidence-package-manifest.sig", Buffer.from(`${signed.signature}\n`, "utf8"));
    // This check closes the ordinary caller-race window. `rename` is atomic
    // because staging and destination share a parent; a competing existing
    // destination is refused rather than intentionally replaced.
    try { await lstat(outputPath); throw new Error("outputDirectory already exists; refusing to overwrite caller-selected output"); } catch (error) {
      if (!(error instanceof Error) || !/ENOENT/.test(String((error as NodeJS.ErrnoException).code))) throw error;
    }
    await rename(join(fdPath(parentHandle), stagingName), outputPath);
    published = true;
    return signed;
  } finally {
    if (stagingHandle !== undefined) await stagingHandle.close();
    if (!published && parentHandle !== undefined && stagingName !== undefined && stagingIdentity !== undefined) {
      const stagingPath = join(fdPath(parentHandle), stagingName);
      try {
        const current = await lstat(stagingPath);
        const uid = typeof process.getuid === "function" ? process.getuid() : undefined;
        if (uid !== undefined && current.isDirectory() && current.uid === uid && current.dev === stagingIdentity.dev && current.ino === stagingIdentity.ino) {
          await rm(stagingPath, { recursive: true, force: true });
        }
      } catch (error) {
        if (!(error instanceof Error) || !/ENOENT/.test(String((error as NodeJS.ErrnoException).code))) throw error;
      }
    }
    if (parentHandle !== undefined) await parentHandle.close();
    releasePublishLock();
  }
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
