import { createHash } from "node:crypto";
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve, relative } from "node:path";
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
  targetPath: string;
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
  sourcePath: string;
  targetPath: string;
  canonicalUri?: string;
  importedAtUtc: string;
  title?: string;
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

async function downloadTo(uri: string, targetPath: string, timeoutMs: number): Promise<void> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(uri, { signal: controller.signal, redirect: "follow" });
    if (!response.ok) throw new Error(`HTTP ${response.status} ${response.statusText}`);
    const bytes = Buffer.from(await response.arrayBuffer());
    if (bytes.length === 0) throw new Error("download returned an empty body");
    await mkdir(dirname(targetPath), { recursive: true });
    await writeFile(targetPath, bytes, { flag: "wx" });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw new Error(`download timed out after ${timeoutMs} ms`);
    throw error instanceof Error ? error : new Error(String(error));
  } finally {
    clearTimeout(timeout);
  }
}

/** Promote and verify an official source, with bounded network access. */
export async function acquireOfficialSource(input: OfficialSourceInput): Promise<SourceRecord> {
  if (!input.canonicalUri.startsWith("https://")) throw new Error("official source URI must use HTTPS");
  assertUtc(input.retrievedAtUtc, "retrievedAtUtc");
  if (input.expectedSha256 !== undefined) assertSha(input.expectedSha256, "expectedSha256");
  const targetPath = resolve(input.targetPath);
  await mkdir(dirname(targetPath), { recursive: true });
  if (input.stagingFile !== undefined) {
    await copyFile(resolve(input.stagingFile), targetPath, 0);
  } else {
    try {
      await downloadTo(input.canonicalUri, targetPath, input.timeoutMs ?? DEFAULT_TIMEOUT_MS);
    } catch (error) {
      throw new Error(`source acquisition blocked for ${input.sourceId}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  const sha256 = await sha256File(targetPath);
  if (input.expectedSha256 !== undefined && sha256 !== input.expectedSha256) {
    throw new Error(`checksum mismatch for ${input.sourceId}: expected ${input.expectedSha256}, got ${sha256}`);
  }
  const record: SourceRecord = {
    sourceId: input.sourceId,
    title: input.title,
    authority: input.authority,
    authorityRank: input.authorityRank,
    canonicalUri: input.canonicalUri,
    localPath: relative(process.cwd(), targetPath),
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
  };
  return assertSourceRecord(record);
}

/** Copy a vault note and add provenance front matter without altering its body. */
export async function copyObsidianNote(input: ObsidianNoteInput): Promise<SourceRecord> {
  assertUtc(input.importedAtUtc, "importedAtUtc");
  const sourcePath = resolve(input.sourcePath);
  const targetPath = resolve(input.targetPath);
  const body = await readFile(sourcePath, "utf8");
  const originalBytes = Buffer.from(body, "utf8");
  const originalSha256 = createHash("sha256").update(originalBytes).digest("hex");
  const frontMatter = [
    "---",
    `originalVaultPath: ${JSON.stringify(input.sourcePath)}`,
    `originalSha256: ${JSON.stringify(originalSha256)}`,
    `importedAtUtc: ${JSON.stringify(input.importedAtUtc)}`,
    "evidenceStatus: \"candidate-context-only\"",
    "---",
    "",
  ].join("\n");
  await mkdir(dirname(targetPath), { recursive: true });
  await writeFile(targetPath, `${frontMatter}${body}`, { flag: "w" });
  const title = input.title ?? input.sourcePath.split("/").pop() ?? input.sourceId;
  return {
    sourceId: input.sourceId,
    title,
    authority: "Local Obsidian knowledge vault",
    authorityRank: 7,
    canonicalUri: input.canonicalUri ?? `https://obsidian.local/vault/${encodeURIComponent(input.sourcePath)}`,
    localPath: relative(process.cwd(), targetPath),
    mediaType: "text/markdown",
    language: "multi",
    retrievedAtUtc: input.importedAtUtc,
    sha256: createHash("sha256").update(frontMatter).update(originalBytes).digest("hex"),
    sensitivity: "unclassified-controlled",
    licenseOrRestriction: "Internal candidate context; do not treat as regulatory authority",
    review: "unreviewed",
  };
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
