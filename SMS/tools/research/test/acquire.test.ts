import { createHash } from "node:crypto";
import { mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { acquireOfficialSource, copyObsidianNote, verifyChecksum } from "../src/acquire.js";
import { verifyOffline } from "../src/cli.js";

const rac94Sha = "312458744b5e4f5097492d4b1c58b0e05229cc5e738058c757d4464e0f155976";
const hash = (value: string) => createHash("sha256").update(value).digest("hex");

async function tempRoot(prefix: string): Promise<string> { return mkdtemp(join(tmpdir(), prefix)); }

afterEach(() => vi.unstubAllGlobals());

describe("research acquisition", () => {
  it("promotes a staging file only when its expected hash matches", async () => {
    const root = await tempRoot("fac-isr-research-");
    try {
      const source = join(root, "racae.pdf");
      await writeFile(source, await readFile(join(process.cwd(), "../../docs/regulations/original/racae_94_enmienda_2_reglas_de_vuelo_y_operacion_uasrpas_0.pdf")));
      const record = await acquireOfficialSource({
        sourceId: "racae-94-enm2" as never, title: "RACAE 94 Enmienda 2", authority: "AAAES", authorityRank: 1,
        canonicalUri: "https://aaaes.fac.mil.co/racae.pdf", targetPath: "docs/racae.pdf", workspaceRoot: root, stagingFile: source,
        language: "es", mediaType: "application/pdf", licenseOrRestriction: "Official public source", retrievedAtUtc: "2026-08-08T17:00:00Z", expectedSha256: rac94Sha,
      });
      expect(record.sha256).toBe(rac94Sha);
      await expect(verifyChecksum(join(root, "docs/racae.pdf"), rac94Sha)).resolves.toBe(true);
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  it("rejects traversal and existing immutable targets", async () => {
    const root = await tempRoot("fac-isr-path-");
    try {
      const source = join(root, "source.pdf"); await writeFile(source, "bytes");
      const base = { sourceId: "source" as never, title: "Source", authority: "AAAES", authorityRank: 1 as const, canonicalUri: "https://example.test/a.pdf", workspaceRoot: root, stagingFile: source, language: "es" as const, mediaType: "application/pdf", licenseOrRestriction: "public", retrievedAtUtc: "2026-08-08T17:00:00Z", expectedSha256: hash("bytes") };
      await expect(acquireOfficialSource({ ...base, targetPath: "../escape.pdf" })).rejects.toThrow("escapes the workspace root");
      await writeFile(join(root, "existing.pdf"), "old");
      await expect(acquireOfficialSource({ ...base, targetPath: "existing.pdf" })).rejects.toThrow("refuses existing target");
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  it("cleans a checksum-mismatched temporary download without promoting it", async () => {
    const root = await tempRoot("fac-isr-mismatch-");
    try {
      const source = join(root, "source.pdf"); await writeFile(source, "wrong bytes");
      await expect(acquireOfficialSource({
        sourceId: "source" as never, title: "Source", authority: "AAAES", authorityRank: 1, canonicalUri: "https://example.test/a.pdf", targetPath: "docs/target.pdf", workspaceRoot: root, stagingFile: source,
        language: "es", mediaType: "application/pdf", licenseOrRestriction: "public", retrievedAtUtc: "2026-08-08T17:00:00Z", expectedSha256: hash("expected bytes"),
      })).rejects.toThrow("checksum mismatch");
      await expect(readFile(join(root, "docs/target.pdf"))).rejects.toThrow();
      expect((await readdir(join(root, "docs"))).filter((name) => name.includes(".partial-")).length).toBe(0);
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  it("cleans a timed-out network temporary file without promoting it", async () => {
    const root = await tempRoot("fac-isr-timeout-");
    try {
      vi.stubGlobal("fetch", (_url: string, options: { signal: AbortSignal }) => new Promise((_resolve, reject) => {
        options.signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
      }));
      await expect(acquireOfficialSource({
        sourceId: "source" as never, title: "Source", authority: "AAAES", authorityRank: 1, canonicalUri: "https://example.test/a.pdf", targetPath: "docs/target.pdf", workspaceRoot: root,
        language: "es", mediaType: "application/pdf", licenseOrRestriction: "public", retrievedAtUtc: "2026-08-08T17:00:00Z", timeoutMs: 1,
      })).rejects.toThrow("timed out");
      await expect(readFile(join(root, "docs/target.pdf"))).rejects.toThrow();
      expect((await readdir(join(root, "docs"))).filter((name) => name.includes(".partial-")).length).toBe(0);
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  it("cleans a failed network acquisition without promoting it", async () => {
    const root = await tempRoot("fac-isr-network-error-");
    try {
      vi.stubGlobal("fetch", () => Promise.reject(new Error("network unavailable")));
      await expect(acquireOfficialSource({
        sourceId: "source" as never, title: "Source", authority: "AAAES", authorityRank: 1, canonicalUri: "https://example.test/a.pdf", targetPath: "docs/target.pdf", workspaceRoot: root,
        language: "es", mediaType: "application/pdf", licenseOrRestriction: "public", retrievedAtUtc: "2026-08-08T17:00:00Z",
      })).rejects.toThrow("source acquisition blocked");
      await expect(readFile(join(root, "docs/target.pdf"))).rejects.toThrow();
      expect((await readdir(join(root, "docs"))).filter((name) => name.includes(".partial-")).length).toBe(0);
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  it("validates official metadata before promotion so an invalid record can be retried", async () => {
    const root = await tempRoot("fac-isr-official-metadata-");
    try {
      const source = join(root, "source.pdf"); await writeFile(source, "official bytes");
      const input = {
        sourceId: "" as never, title: "Official source", authority: "AAAES", authorityRank: 1 as const,
        canonicalUri: "https://example.test/official.pdf", targetPath: "docs/official.pdf", workspaceRoot: root,
        stagingFile: source, language: "es" as const, mediaType: "application/pdf", licenseOrRestriction: "public",
        retrievedAtUtc: "2026-08-08T17:00:00Z", expectedSha256: hash("official bytes"),
      };
      await expect(acquireOfficialSource(input)).rejects.toThrow("missing a required non-empty string");
      await expect(readFile(join(root, "docs/official.pdf"))).rejects.toThrow();

      const record = await acquireOfficialSource({ ...input, sourceId: "official-retry" as never });
      expect(record.sourceId).toBe("official-retry");
      await expect(verifyChecksum(join(root, "docs/official.pdf"), hash("official bytes"))).resolves.toBe(true);
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  it("preserves vault provenance in generated front matter and rejects unsafe targets", async () => {
    const root = await tempRoot("fac-isr-note-");
    try {
      const source = join(root, "source.md"); await writeFile(source, "# Candidate\n\nSpanish source context.\n", "utf8");
      const record = await copyObsidianNote({ sourceId: "obsidian-candidate" as never, sourcePath: source, originalVaultPath: "Vault/source.md", targetPath: "imports/import.md", workspaceRoot: root, importedAtUtc: "2026-08-08T17:00:00Z" });
      const imported = await readFile(join(root, "imports/import.md"), "utf8");
      expect(imported.startsWith("---\noriginalVaultPath: \"Vault/source.md\"")).toBe(true);
      expect(imported.endsWith("# Candidate\n\nSpanish source context.\n")).toBe(true);
      expect(record.review).toBe("unreviewed");
      await expect(copyObsidianNote({ sourceId: "unsafe" as never, sourcePath: source, targetPath: "../escape.md", workspaceRoot: root, importedAtUtc: "2026-08-08T17:00:00Z" })).rejects.toThrow("escapes the workspace root");
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  it("validates Obsidian metadata before promotion so an invalid record can be retried", async () => {
    const root = await tempRoot("fac-isr-note-metadata-");
    try {
      const source = join(root, "source.md"); await writeFile(source, "# Candidate\n", "utf8");
      const input = {
        sourceId: "" as never, sourcePath: source, originalVaultPath: "Vault/source.md", targetPath: "imports/import.md",
        workspaceRoot: root, importedAtUtc: "2026-08-08T17:00:00Z",
      };
      await expect(copyObsidianNote(input)).rejects.toThrow("missing a required non-empty string");
      await expect(readFile(join(root, "imports/import.md"))).rejects.toThrow();

      const record = await copyObsidianNote({ ...input, sourceId: "obsidian-retry" as never });
      expect(record.sourceId).toBe("obsidian-retry");
      await expect(readFile(join(root, "imports/import.md"), "utf8")).resolves.toContain("originalVaultPath");
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  it("verifies records and their registered extraction artifacts offline", async () => {
    const root = await tempRoot("fac-isr-offline-");
    try {
      await writeFile(join(root, "primary.txt"), "primary"); await writeFile(join(root, "extract.txt"), "extracted");
      const record = { sourceId: "primary" as never, title: "Primary", authority: "AAAES", authorityRank: 1, canonicalUri: "https://example.test/primary", localPath: "primary.txt", mediaType: "text/plain", language: "es", retrievedAtUtc: "2026-08-08T17:00:00Z", sha256: hash("primary"), extractionPath: "extract.txt", extractionSha256: hash("extracted"), sensitivity: "unclassified-controlled", licenseOrRestriction: "public", review: "in-review" };
      const register = join(root, "sources.jsonl"); await writeFile(register, `${JSON.stringify(record)}\n`);
      await expect(verifyOffline(root, register)).resolves.toEqual([]);
      await writeFile(join(root, "extract.txt"), "tampered");
      await expect(verifyOffline(root, register)).resolves.toEqual(["primary: extraction checksum mismatch"]);
      await writeFile(join(root, "extract.txt"), "extracted");
      await writeFile(join(root, "primary.txt"), "tampered");
      await expect(verifyOffline(root, register)).resolves.toEqual(["primary: primary checksum mismatch"]);
      await writeFile(register, `${JSON.stringify({ ...record, localPath: "../escape.txt" })}\n`);
      await expect(verifyOffline(root, register)).resolves.toEqual([expect.stringContaining("primary artifact unavailable: primary.localPath escapes the workspace root")]);
      await writeFile(register, `${JSON.stringify({ sourceId: "malformed" })}\n`);
      await expect(verifyOffline(root, register)).resolves.toEqual([expect.stringContaining("malformed source record")]);
    } finally { await rm(root, { recursive: true, force: true }); }
  });
});
