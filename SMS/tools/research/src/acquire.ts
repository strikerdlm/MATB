import { createHash, randomUUID } from "node:crypto";
import { access, copyFile, link, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { assertSourceRecord, sha256File } from "@fac-isr/evidence";
import type { SourceRecord, SourceId } from "@fac-isr/evidence";

const SHA256 = /^[a-f0-9]{64}$/;
const DEFAULT_TIMEOUT_MS = 30_000;
const ISO_UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/;

export interface OfficialSourceInput {
  sourceId: SourceId;
  title: string;
  authority: string;
  authorityRank: SourceRecord["authorityRank"];
  canonicalUri: string;
  /** A workspace-relative destination; absolute and traversal paths are rejected. */
  targetPath: string;
  workspaceRoot?: string;
  language: SourceRecord["language"];
  mediaType: string;
  licenseOrRestriction: string;
  retrievedAtUtc: string;
  publicationDate?: string;
  amendmentDate?: string;
  effectiveFromUtc?: string;
  expectedSha256?: string;
  /** A known-good staging file can be promoted without network access. */
  stagingFile?: string;
  timeoutMs?: number;
  review?: SourceRecord["review"];
}

export interface ObsidianNoteInput {
  sourceId: SourceId;
  /** Absolute or vault-relative input path; this is read-only source material. */
  sourcePath: string;
  /** Stable vault-relative provenance label; never use an absolute path in metadata. */
  originalVaultPath?: string;
  /** A workspace-relative destination; absolute and traversal paths are rejected. */
  targetPath: string;
  workspaceRoot?: string;
  canonicalUri?: string;
  importedAtUtc: string;
  title?: string;
  redactionRequired?: boolean;
}

export interface AcquisitionStatus {
  sourceId: string;
  canonicalUri: string;
  targetPath: string;
  availability: "available" | "blocked";
  retrievedAtUtc: string;
  sha256?: string;
  error?: string;
}

function assertUtc(value: string, field: string): void {
  if (!ISO_UTC.test(value) || Number.isNaN(Date.parse(value))) throw new Error(`${field} must be an exact UTC timestamp`);
}

function assertSha(value: string, field: string): void {
  if (!SHA256.test(value)) throw new Error(`${field} must be a SHA-256 hex digest`);
}

/** Resolve an artifact only within the selected workspace, with no path traversal. */
export function resolveWorkspacePath(workspaceRoot: string, candidate: string, field = "targetPath"): string {
  if (!candidate || isAbsolute(candidate)) throw new Error(`${field} must be a non-empty workspace-relative path`);
  const root = resolve(workspaceRoot);
  const target = resolve(root, candidate);
  const fromRoot = relative(root, target);
  if (fromRoot === "" || fromRoot === ".." || fromRoot.startsWith(`..${sep}`) || isAbsolute(fromRoot)) {
    throw new Error(`${field} escapes the workspace root`);
  }
  return target;
}

async function assertNewTarget(targetPath: string): Promise<void> {
  try {
    await access(targetPath);
    throw new Error(`immutable promotion refuses existing target: ${targetPath}`);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return;
    throw error;
  }
}

async function promoteTempFile(tempPath: string, targetPath: string): Promise<void> {
  await assertNewTarget(targetPath);
  try {
    // link() is an atomic no-overwrite promotion on the same filesystem.
    await link(tempPath, targetPath);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "EEXIST") throw new Error(`immutable promotion refuses existing target: ${targetPath}`);
    throw error;
  } finally {
    await rm(tempPath, { force: true });
  }
}

async function downloadTo(uri: string, tempPath: string, timeoutMs: number): Promise<void> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(uri, { signal: controller.signal, redirect: "follow" });
    if (!response.ok) throw new Error(`HTTP ${response.status} ${response.statusText}`);
    const bytes = Buffer.from(await response.arrayBuffer());
    if (bytes.length === 0) throw new Error("download returned an empty body");
    await writeFile(tempPath, bytes, { flag: "wx" });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw new Error(`download timed out after ${timeoutMs} ms`);
    throw error instanceof Error ? error : new Error(String(error));
  } finally {
    clearTimeout(timeout);
  }
}

/** Promote and verify an official source without ever leaving unverified bytes at its final path. */
export async function acquireOfficialSource(input: OfficialSourceInput): Promise<SourceRecord> {
  if (!input.canonicalUri.startsWith("https://")) throw new Error("official source URI must use HTTPS");
  assertUtc(input.retrievedAtUtc, "retrievedAtUtc");
  if (input.effectiveFromUtc !== undefined) assertUtc(input.effectiveFromUtc, "effectiveFromUtc");
  if (input.expectedSha256 !== undefined) assertSha(input.expectedSha256, "expectedSha256");
  const workspaceRoot = resolve(input.workspaceRoot ?? process.cwd());
  const targetPath = resolveWorkspacePath(workspaceRoot, input.targetPath);
  await mkdir(dirname(targetPath), { recursive: true });
  await assertNewTarget(targetPath);
  const tempPath = `${targetPath}.partial-${randomUUID()}`;
  try {
    if (input.stagingFile !== undefined) {
      await copyFile(resolve(input.stagingFile), tempPath);
    } else {
      try {
        await downloadTo(input.canonicalUri, tempPath, input.timeoutMs ?? DEFAULT_TIMEOUT_MS);
      } catch (error) {
        throw new Error(`source acquisition blocked for ${input.sourceId}: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
    const sha256 = await sha256File(tempPath);
    if (input.expectedSha256 !== undefined && sha256 !== input.expectedSha256) {
      throw new Error(`checksum mismatch for ${input.sourceId}: expected ${input.expectedSha256}, got ${sha256}`);
    }
    await promoteTempFile(tempPath, targetPath);
    return assertSourceRecord({
      sourceId: input.sourceId,
      title: input.title,
      authority: input.authority,
      authorityRank: input.authorityRank,
      canonicalUri: input.canonicalUri,
      localPath: relative(workspaceRoot, targetPath),
      mediaType: input.mediaType,
      language: input.language,
      publicationDate: input.publicationDate,
      amendmentDate: input.amendmentDate,
      effectiveFromUtc: input.effectiveFromUtc,
      retrievedAtUtc: input.retrievedAtUtc,
      sha256,
      sensitivity: "unclassified-controlled",
      licenseOrRestriction: input.licenseOrRestriction,
      review: input.review ?? "in-review",
    });
  } catch (error) {
    await rm(tempPath, { force: true });
    throw error;
  }
}

/** Copy a vault note with generated provenance front matter, preserving every body byte. */
export async function copyObsidianNote(input: ObsidianNoteInput): Promise<SourceRecord> {
  assertUtc(input.importedAtUtc, "importedAtUtc");
  const workspaceRoot = resolve(input.workspaceRoot ?? process.cwd());
  const targetPath = resolveWorkspacePath(workspaceRoot, input.targetPath);
  const sourcePath = resolve(input.sourcePath);
  const originalVaultPath = input.originalVaultPath ?? input.sourcePath;
  if (!originalVaultPath || isAbsolute(originalVaultPath) || originalVaultPath.split(/[\\/]/).includes("..")) {
    throw new Error("originalVaultPath must be a non-empty vault-relative path");
  }
  const body = await readFile(sourcePath, "utf8");
  const originalBytes = Buffer.from(body, "utf8");
  const originalSha256 = createHash("sha256").update(originalBytes).digest("hex");
  const frontMatter = [
    "---",
    `originalVaultPath: ${JSON.stringify(originalVaultPath)}`,
    `originalSha256: ${JSON.stringify(originalSha256)}`,
    `importedAtUtc: ${JSON.stringify(input.importedAtUtc)}`,
    "evidenceStatus: \"candidate-context-only\"",
    ...(input.redactionRequired ? ["redactionRequired: true"] : []),
    "---",
    "",
  ].join("\n");
  await mkdir(dirname(targetPath), { recursive: true });
  await assertNewTarget(targetPath);
  const tempPath = `${targetPath}.partial-${randomUUID()}`;
  try {
    await writeFile(tempPath, `${frontMatter}${body}`, { flag: "wx" });
    await promoteTempFile(tempPath, targetPath);
  } catch (error) {
    await rm(tempPath, { force: true });
    throw error;
  }
  const title = input.title ?? originalVaultPath.split("/").pop() ?? input.sourceId;
  return assertSourceRecord({
    sourceId: input.sourceId,
    title,
    authority: "Local Obsidian knowledge vault",
    authorityRank: 7,
    canonicalUri: input.canonicalUri ?? `https://obsidian.local/vault/${encodeURIComponent(originalVaultPath)}`,
    localPath: relative(workspaceRoot, targetPath),
    mediaType: "text/markdown",
    language: "multi",
    retrievedAtUtc: input.importedAtUtc,
    sha256: createHash("sha256").update(frontMatter).update(originalBytes).digest("hex"),
    sensitivity: "unclassified-controlled",
    licenseOrRestriction: input.redactionRequired
      ? "Internal candidate context; redaction required before any broader distribution; do not operationalize"
      : "Internal candidate context; do not treat as regulatory authority",
    review: "unreviewed",
  });
}

export async function verifyChecksum(path: string, expectedSha256: string): Promise<boolean> {
  assertSha(expectedSha256, "expectedSha256");
  return (await sha256File(resolve(path))) === expectedSha256;
}

export async function extractText(pdfPath: string, outputPath: string): Promise<string> {
  const { execFile } = await import("node:child_process");
  const { promisify } = await import("node:util");
  const run = promisify(execFile);
  await mkdir(dirname(resolve(outputPath)), { recursive: true });
  await run("pdftotext", ["-layout", resolve(pdfPath), resolve(outputPath)]);
  return sha256File(resolve(outputPath));
}
