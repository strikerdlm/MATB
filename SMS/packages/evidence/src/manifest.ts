import { createHash, sign, verify } from "node:crypto";
import { lstat, readdir, stat } from "node:fs/promises";
import { isAbsolute, relative, resolve, sep } from "node:path";
import { canonicalJson, sha256File } from "./hash.js";
import type { ManifestFile, SignedPackageManifest } from "./types.js";

const SHA256 = /^[a-f0-9]{64}$/;
const PACKAGE_ID = /^[a-z0-9][a-z0-9._-]{2,127}$/;
// Evidence package versions are immutable release versions. Prerelease
// labels are intentionally rejected until a complete SemVer comparator and
// promotion policy exist; this prevents 1.0.0-alpha being treated as 1.0.0.
const VERSION = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const UTC = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{3})?Z$/;
const CONTROL_FILES = new Set(["evidence-package-manifest.json", "evidence-package-manifest.sig", "evidence-package-public-key.pem"]);

export interface VerificationCheck { id: string; status: "pass" | "fail" | "warn"; reason?: string; }
export interface VerificationReport { ok: boolean; checks: readonly VerificationCheck[]; packageId: string; }

function isExactUtc(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = UTC.exec(value);
  if (!match) return false;
  const [, y, mo, d, h, mi, s] = match;
  const year = Number(y); const month = Number(mo); const day = Number(d);
  const hour = Number(h); const minute = Number(mi); const second = Number(s);
  if (month < 1 || month > 12 || day < 1 || hour > 23 || minute > 59 || second > 59) return false;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  return day <= [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
}

function assertContainedPath(value: unknown, field: string): asserts value is string {
  if (typeof value !== "string" || value.trim() === "" || isAbsolute(value) || value.includes("\\")) throw new Error(`${field} must be a non-empty relative POSIX path`);
  const normalized = value.split("/");
  if (normalized.some((part) => !part || part === "." || part === "..")) throw new Error(`${field} has path traversal`);
}

const MANIFEST_KINDS = ["regulatory", "policy", "map", "weather", "notam", "terminology", "software"] as const;

/** Validate untrusted manifest JSON before it reaches signing, installation, or verification. */
export function assertSignedPackageManifest(value: unknown, signatureRequired = true): asserts value is SignedPackageManifest {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error("manifest must be an object");
  const manifest = value as SignedPackageManifest;
  if (manifest.schemaVersion !== "1.0") throw new Error("unsupported manifest schemaVersion");
  if (!PACKAGE_ID.test(manifest.packageId)) throw new Error("manifest packageId is invalid");
  if (!(MANIFEST_KINDS as readonly string[]).includes(manifest.kind)) throw new Error("manifest kind is invalid");
  if (!VERSION.test(manifest.version)) throw new Error("manifest version is invalid");
  if (typeof manifest.issuer !== "string" || manifest.issuer.trim() === "") throw new Error("manifest issuer is required");
  if (typeof manifest.keyId !== "string" || manifest.keyId.trim() === "") throw new Error("manifest keyId is required");
  if (typeof manifest.geographicScope !== "string" || manifest.geographicScope.trim() === "") throw new Error("manifest geographicScope is required");
  if (!isExactUtc(manifest.issuedAtUtc) || !isExactUtc(manifest.effectiveFromUtc)) throw new Error("manifest timestamps must be exact UTC");
  if (manifest.expiresAtUtc !== undefined && !isExactUtc(manifest.expiresAtUtc)) throw new Error("manifest expiresAtUtc must be exact UTC");
  if (manifest.expiresAtUtc !== undefined && Date.parse(manifest.expiresAtUtc) <= Date.parse(manifest.effectiveFromUtc)) throw new Error("manifest expiry must be after effective time");
  if (Date.parse(manifest.issuedAtUtc) > Date.parse(manifest.effectiveFromUtc)) throw new Error("manifest issuedAtUtc cannot follow effectiveFromUtc");
  if (!SHA256.test(manifest.contentSha256)) throw new Error("manifest contentSha256 is invalid");
  if (!Array.isArray(manifest.dependencies)) throw new Error("manifest dependencies are invalid");
  let previousDependency = "";
  for (const dependency of manifest.dependencies) {
    if (dependency === null || typeof dependency !== "object" || !PACKAGE_ID.test(dependency.packageId) || !VERSION.test(dependency.version) || !SHA256.test(dependency.contentSha256)) throw new Error("manifest dependency is invalid");
    if (dependency.packageId === manifest.packageId) throw new Error("manifest cannot depend on itself");
    const dependencyKey = `${dependency.packageId}@${dependency.version}#${dependency.contentSha256}`;
    if (previousDependency >= dependencyKey) throw new Error("manifest dependencies must be sorted and unique");
    previousDependency = dependencyKey;
  }
  if (!Array.isArray(manifest.files) || manifest.files.length === 0) throw new Error("manifest files are required");
  if (!Array.isArray(manifest.caveats) || manifest.caveats.some((item) => typeof item !== "string" || item.trim() === "")) throw new Error("manifest caveats are invalid");
  if (!(["qualified-review", "approved", "blocked"] as const).includes(manifest.qualification)) throw new Error("manifest qualification is invalid");
  let previous = "";
  for (const file of manifest.files) {
    if (file === null || typeof file !== "object") throw new Error("manifest file is invalid");
    assertContainedPath(file.path, "manifest file path");
    if (!SHA256.test(file.sha256) || !Number.isSafeInteger(file.sizeBytes) || file.sizeBytes < 0) throw new Error(`manifest file ${file.path} is invalid`);
    if (previous >= file.path) throw new Error("manifest files must be sorted and unique");
    previous = file.path;
  }
  if (signatureRequired && (typeof manifest.signature !== "string" || !/^[A-Za-z0-9+/]+={0,2}$/.test(manifest.signature))) throw new Error("manifest signature is required");
}

export function manifestContentDigest(files: readonly ManifestFile[]): string {
  return createHash("sha256").update(canonicalJson(files)).digest("hex");
}

/** Canonical signature payload. `signature` is always removed, so signing and verification agree. */
export function manifestSigningPayload(manifest: SignedPackageManifest): Buffer {
  const { signature: _signature, ...unsigned } = manifest;
  return Buffer.from(canonicalJson(unsigned), "utf8");
}

/** Sign a fully specified manifest. Private-key material is caller supplied and never persisted here. */
export function signManifest(manifest: Omit<SignedPackageManifest, "signature"> | SignedPackageManifest, privateKey: string | Buffer): SignedPackageManifest {
  const unsigned = { ...manifest, signature: "" } as SignedPackageManifest;
  assertSignedPackageManifest(unsigned, false);
  const computedDigest = manifestContentDigest(unsigned.files);
  if (computedDigest !== unsigned.contentSha256) throw new Error("manifest contentSha256 does not match its file inventory");
  const signature = sign(null, manifestSigningPayload(unsigned), privateKey).toString("base64");
  return Object.freeze({ ...unsigned, signature });
}

async function walkFiles(root: string, current = root): Promise<string[]> {
  const entries = await readdir(current, { withFileTypes: true });
  const output: string[] = [];
  for (const entry of entries) {
    const full = resolve(current, entry.name);
    if (entry.isSymbolicLink()) throw new Error(`symbolic links are not permitted: ${relative(root, full)}`);
    if (entry.isDirectory()) output.push(...await walkFiles(root, full));
    else if (entry.isFile()) output.push(relative(root, full).split(sep).join("/"));
    else throw new Error(`unsupported package entry: ${relative(root, full)}`);
  }
  return output.sort();
}

function resolvePackagePath(root: string, relativePath: string): string {
  assertContainedPath(relativePath, "package file path");
  const full = resolve(root, relativePath);
  const fromRoot = relative(root, full);
  if (fromRoot === "" || fromRoot === ".." || fromRoot.startsWith(`..${sep}`) || isAbsolute(fromRoot)) throw new Error("package file path escapes package root");
  return full;
}

export async function verifyPackage(directory: string, manifest: SignedPackageManifest, publicKey: string | Buffer, asOfUtc: string, availableDependencies: readonly SignedPackageManifest[] = []): Promise<VerificationReport> {
  const checks: VerificationCheck[] = [];
  const fail = (id: string, reason: string): void => { checks.push({ id, status: "fail", reason }); };
  try { assertSignedPackageManifest(manifest, true); checks.push({ id: "manifest-shape", status: "pass" }); } catch (error) { fail("manifest-shape", error instanceof Error ? error.message : String(error)); return { ok: false, checks, packageId: typeof manifest?.packageId === "string" ? manifest.packageId : "unknown" }; }
  if (!isExactUtc(asOfUtc)) { fail("as-of", "asOfUtc must be an exact UTC timestamp"); return { ok: false, checks, packageId: manifest.packageId }; }
  const now = Date.parse(asOfUtc);
  if (now < Date.parse(manifest.effectiveFromUtc)) fail("effective-window", "package is not yet effective");
  else if (manifest.expiresAtUtc !== undefined && now >= Date.parse(manifest.expiresAtUtc)) fail("effective-window", "package is expired");
  else checks.push({ id: "effective-window", status: "pass" });
  if (manifestContentDigest(manifest.files) !== manifest.contentSha256) fail("content-digest", "file inventory digest mismatch"); else checks.push({ id: "content-digest", status: "pass" });
  if (!verify(null, manifestSigningPayload(manifest), publicKey, Buffer.from(manifest.signature, "base64"))) fail("signature", "invalid manifest signature"); else checks.push({ id: "signature", status: "pass" });
  const available = new Set(availableDependencies.map((dependency) => `${dependency.packageId}@${dependency.version}#${dependency.contentSha256}`));
  const unavailable = manifest.dependencies.filter((dependency) => !available.has(`${dependency.packageId}@${dependency.version}#${dependency.contentSha256}`));
  if (unavailable.length) fail("dependencies", `dependency mismatch: ${unavailable.map((dependency) => dependency.packageId).join(", ")}`); else checks.push({ id: "dependencies", status: "pass" });
  const root = resolve(directory);
  try {
    const expected = new Set(manifest.files.map((file) => file.path));
    const actual = (await walkFiles(root)).filter((file) => !CONTROL_FILES.has(file));
    const extra = actual.filter((file) => !expected.has(file));
    const missing = [...expected].filter((file) => !actual.includes(file));
    if (extra.length || missing.length) fail("file-set", `${missing.length ? `missing: ${missing.join(", ")}` : ""}${extra.length ? `${missing.length ? "; " : ""}extra: ${extra.join(", ")}` : ""}`);
    else checks.push({ id: "file-set", status: "pass" });
    for (const file of manifest.files) {
      const path = resolvePackagePath(root, file.path);
      const info = await stat(path);
      if (!info.isFile() || info.size !== file.sizeBytes || (await sha256File(path)) !== file.sha256) fail(`file:${file.path}`, "file hash or size mismatch");
      else checks.push({ id: `file:${file.path}`, status: "pass" });
    }
  } catch (error) { fail("file-set", error instanceof Error ? error.message : String(error)); }
  return { ok: !checks.some((check) => check.status === "fail"), checks, packageId: manifest.packageId };
}

function releaseVersion(version: string): number[] {
  return version.split(".").map(Number);
}

/** Refuse replacement of an installed package by an earlier version or effective period. */
export function rejectDowngrade(current: SignedPackageManifest, incoming: SignedPackageManifest): void {
  assertSignedPackageManifest(current, true); assertSignedPackageManifest(incoming, true);
  if (current.packageId !== incoming.packageId) throw new Error("downgrade comparison requires matching package IDs");
  if (Date.parse(incoming.effectiveFromUtc) < Date.parse(current.effectiveFromUtc)) throw new Error("downgrade rejected: incoming effective period is older");
  const installed = releaseVersion(current.version); const candidate = releaseVersion(incoming.version);
  for (let index = 0; index < installed.length; index += 1) {
    if (candidate[index] < installed[index]) throw new Error("downgrade rejected: incoming version is older");
    if (candidate[index] > installed[index]) return;
  }
  if (incoming.contentSha256 !== current.contentSha256) throw new Error("downgrade rejected: same version has different content");
}
