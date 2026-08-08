import { appendFile, mkdir, readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { assertSourceRecord, sha256File } from "@fac-isr/evidence";
import type { SourceRecord } from "@fac-isr/evidence";
import { acquireOfficialSource, copyObsidianNote, extractText, resolveWorkspacePath, verifyChecksum } from "./acquire.js";

/** CLI is intentionally run from the SMS workspace root (`cd SMS`). */
const ROOT = resolve(process.cwd());
const REGISTER = resolve(ROOT, "docs/source-register/sources.jsonl");
const QUERY_LOG = resolve(ROOT, "docs/research/query-log.jsonl");
const QUERY_STATUS = ["pending", "executed", "unverified-lead"] as const;
type QueryStatus = (typeof QUERY_STATUS)[number];

function arg(name: string): string | undefined {
  const index = process.argv.indexOf(`--${name}`);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

async function appendJsonl(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  await appendFile(path, `${JSON.stringify(value)}\n`, "utf8");
}

function parseLines(contents: string): unknown[] {
  return contents.trim().split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
}

/** Deterministically validate all registered artifacts without reaching the network. */
export async function verifyOffline(root = ROOT, registerPath = resolve(root, "docs/source-register/sources.jsonl")): Promise<string[]> {
  let sources: unknown[];
  try {
    sources = parseLines(await readFile(registerPath, "utf8"));
  } catch (error) {
    return [`source register: ${error instanceof Error ? error.message : String(error)}`];
  }
  const failures: string[] = [];
  for (const raw of sources) {
    const label = raw !== null && typeof raw === "object" && "sourceId" in raw ? String((raw as { sourceId?: unknown }).sourceId) : "unknown";
    let source: SourceRecord;
    try {
      source = assertSourceRecord(raw);
    } catch (error) {
      failures.push(`${label}: malformed source record: ${error instanceof Error ? error.message : String(error)}`);
      continue;
    }
    try {
      const primaryPath = resolveWorkspacePath(root, source.localPath, `${source.sourceId}.localPath`);
      if (!(await verifyChecksum(primaryPath, source.sha256))) {
        failures.push(`${source.sourceId}: primary checksum mismatch`);
      }
    } catch (error) {
      failures.push(`${source.sourceId}: primary artifact unavailable: ${error instanceof Error ? error.message : String(error)}`);
    }
    if (source.extractionSha256 !== undefined && source.extractionPath === undefined) {
      failures.push(`${source.sourceId}: missing extraction artifact mapping`);
    } else if (source.extractionSha256 !== undefined && source.extractionPath !== undefined) {
      try {
        const extractionPath = resolveWorkspacePath(root, source.extractionPath, `${source.sourceId}.extractionPath`);
        if ((await sha256File(extractionPath)) !== source.extractionSha256) {
          failures.push(`${source.sourceId}: extraction checksum mismatch`);
        }
      } catch (error) {
        failures.push(`${source.sourceId}: extraction artifact unavailable: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
  }
  return failures;
}

async function main(): Promise<void> {
  const command = process.argv[2];
  if (command === "record-query") {
    const query = arg("query");
    const tool = arg("tool");
    const status = (arg("status") ?? "pending") as QueryStatus;
    const evidenceArtifact = arg("evidence-artifact");
    if (!query || !tool) throw new Error("record-query requires --tool and --query");
    if (!QUERY_STATUS.includes(status)) throw new Error(`record-query status must be one of: ${QUERY_STATUS.join(", ")}`);
    if (status === "executed" && !evidenceArtifact) throw new Error("record-query executed status requires --evidence-artifact");
    await appendJsonl(QUERY_LOG, {
      recordedAtUtc: arg("recorded-at") ?? new Date().toISOString(),
      tool,
      query,
      filters: arg("filters") ?? "",
      resultUrls: (arg("urls") ?? "").split(",").filter(Boolean),
      resultSummary: arg("summary") ?? "",
      reviewer: arg("reviewer") ?? "pending-independent-review",
      status,
      ...(evidenceArtifact ? { evidenceArtifact } : {}),
    });
    return;
  }
  if (command === "acquire") {
    const record = await acquireOfficialSource({
      sourceId: arg("source-id") as never,
      title: arg("title") ?? "Official source",
      authority: arg("authority") ?? "AAAES",
      authorityRank: 1,
      canonicalUri: arg("uri") ?? "",
      targetPath: arg("target") ?? "",
      workspaceRoot: ROOT,
      language: "es",
      mediaType: arg("media-type") ?? "application/pdf",
      licenseOrRestriction: arg("license") ?? "Official public source; verify reuse terms",
      retrievedAtUtc: arg("retrieved-at") ?? new Date().toISOString(),
      expectedSha256: arg("sha256"),
      stagingFile: arg("staging-file"),
      timeoutMs: Number(arg("timeout-ms") ?? 30_000),
    });
    await appendJsonl(REGISTER, record);
    return;
  }
  if (command === "copy-obsidian") {
    const record = await copyObsidianNote({
      sourceId: arg("source-id") as never,
      sourcePath: arg("source") ?? "",
      originalVaultPath: arg("original-vault-path"),
      targetPath: arg("target") ?? "",
      workspaceRoot: ROOT,
      importedAtUtc: arg("imported-at") ?? new Date().toISOString(),
      redactionRequired: arg("redaction-required") === "true",
    });
    await appendJsonl(REGISTER, record);
    return;
  }
  if (command === "extract") {
    const outputHash = await extractText(arg("source") ?? "", arg("target") ?? "");
    process.stdout.write(`${outputHash}\n`);
    return;
  }
  if (command === "verify") {
    const ok = await verifyChecksum(arg("source") ?? "", arg("sha256") ?? "");
    if (!ok) throw new Error("checksum verification failed");
    process.stdout.write("PASS\n");
    return;
  }
  if (command === "verify-offline") {
    const failures = await verifyOffline();
    if (failures.length > 0) { process.stderr.write(`${failures.join("\n")}\n`); process.exitCode = 1; return; }
    process.stdout.write("PASS offline source verification\n");
    return;
  }
  throw new Error(`unknown research command: ${command ?? "(missing)"}`);
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error: unknown) => { process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`); process.exitCode = 1; });
}
