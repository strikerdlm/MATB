import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { sha256File } from "@fac-isr/evidence";
import { acquireOfficialSource, copyObsidianNote, extractText, verifyChecksum } from "./acquire.js";

/** CLI is intentionally run from the SMS workspace root (`cd SMS`). */
const ROOT = resolve(process.cwd());
const REGISTER = resolve(ROOT, "docs/source-register/sources.jsonl");
const QUERY_LOG = resolve(ROOT, "docs/research/query-log.jsonl");

function arg(name: string): string | undefined {
  const index = process.argv.indexOf(`--${name}`);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

async function appendJsonl(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  await appendFile(path, `${JSON.stringify(value)}\n`, "utf8");
}

async function main(): Promise<void> {
  const command = process.argv[2];
  if (command === "record-query") {
    const query = arg("query");
    const tool = arg("tool");
    if (!query || !tool) throw new Error("record-query requires --tool and --query");
    await appendJsonl(QUERY_LOG, {
      recordedAtUtc: arg("recorded-at") ?? new Date().toISOString(),
      tool,
      query,
      filters: arg("filters") ?? "",
      resultUrls: (arg("urls") ?? "").split(",").filter(Boolean),
      resultSummary: arg("summary") ?? "",
      reviewer: arg("reviewer") ?? "pending-independent-review",
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
      targetPath: arg("target") ?? "",
      importedAtUtc: arg("imported-at") ?? new Date().toISOString(),
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
    const sources = (await readFile(REGISTER, "utf8")).trim().split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line) as { localPath?: string; sha256?: string; sourceId?: string });
    const failures: string[] = [];
    for (const source of sources) {
      if (!source.localPath || !source.sha256) { failures.push(`${source.sourceId ?? "unknown"}: missing provenance`); continue; }
      try {
        if (!(await verifyChecksum(resolve(ROOT, source.localPath), source.sha256))) failures.push(`${source.sourceId}: checksum mismatch`);
      } catch (error) { failures.push(`${source.sourceId ?? "unknown"}: ${error instanceof Error ? error.message : String(error)}`); }
    }
    if (failures.length > 0) { process.stderr.write(`${failures.join("\n")}\n`); process.exitCode = 1; return; }
    process.stdout.write(`PASS ${sources.length} source records\n`);
    return;
  }
  throw new Error(`unknown research command: ${command ?? "(missing)"}`);
}

main().catch((error: unknown) => { process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`); process.exitCode = 1; });
