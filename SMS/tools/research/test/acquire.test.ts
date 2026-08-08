import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { acquireOfficialSource, copyObsidianNote, verifyChecksum } from "../src/acquire.js";

const sha = "312458744b5e4f5097492d4b1c58b0e05229cc5e738058c757d4464e0f155976";

describe("research acquisition", () => {
  it("promotes a staging file only when its expected hash matches", async () => {
    const root = await mkdtemp(join(tmpdir(), "fac-isr-research-"));
    try {
      const source = join(root, "racae.pdf");
      const target = join(root, "docs", "racae.pdf");
      await writeFile(source, await readFile(join(process.cwd(), "../../docs/regulations/original/racae_94_enmienda_2_reglas_de_vuelo_y_operacion_uasrpas_0.pdf")));
      const record = await acquireOfficialSource({
        sourceId: "racae-94-enm2" as never,
        title: "RACAE 94 Enmienda 2",
        authority: "AAAES",
        authorityRank: 1,
        canonicalUri: "https://aaaes.fac.mil.co/racae.pdf",
        targetPath: target,
        stagingFile: source,
        language: "es",
        mediaType: "application/pdf",
        licenseOrRestriction: "Official public source",
        retrievedAtUtc: "2026-08-08T17:00:00Z",
        expectedSha256: sha,
      });
      expect(record.sha256).toBe(sha);
      await expect(verifyChecksum(target, sha)).resolves.toBe(true);
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  it("preserves vault provenance when importing a note", async () => {
    const root = await mkdtemp(join(tmpdir(), "fac-isr-note-"));
    try {
      const source = join(root, "source.md"); const target = join(root, "import.md");
      await writeFile(source, "# Candidate\n\nSpanish source context.\n", "utf8");
      const record = await copyObsidianNote({ sourceId: "obsidian-candidate" as never, sourcePath: source, targetPath: target, importedAtUtc: "2026-08-08T17:00:00Z" });
      const imported = await readFile(target, "utf8");
      expect(imported).toContain("originalVaultPath");
      expect(imported).toContain("# Candidate");
      expect(record.review).toBe("unreviewed");
    } finally { await rm(root, { recursive: true, force: true }); }
  });
});
