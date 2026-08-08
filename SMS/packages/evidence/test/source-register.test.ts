import { describe, expect, it } from "vitest";
import { SourceRegister } from "../src/index.js";
import type { SourceRecord } from "../src/types.js";

const validRecord: SourceRecord = {
  sourceId: "source-a" as SourceRecord["sourceId"],
  title: "Reviewed source",
  authority: "FAC",
  authorityRank: 1,
  canonicalUri: "https://example.gov/source-a.pdf",
  localPath: "docs/source-a.pdf",
  mediaType: "application/pdf",
  language: "es",
  retrievedAtUtc: "2026-08-08T12:00:00Z",
  sha256: "a".repeat(64),
  extractionSha256: "b".repeat(64),
  sensitivity: "unclassified-controlled",
  licenseOrRestriction: "Official public source",
  review: "accepted",
};

describe("SourceRegister", () => {
  it("rejects a second write for an existing source ID", () => {
    const register = new SourceRegister();
    register.append(validRecord);
    expect(() => register.append({ ...validRecord, sha256: "c".repeat(64) })).toThrow("immutable");
  });

  it("freezes records, lists active sources in source-ID order, and round trips JSONL", () => {
    const register = new SourceRegister();
    register.append({ ...validRecord, sourceId: "source-z" as SourceRecord["sourceId"] });
    register.append({ ...validRecord, sourceId: "source-a2" as SourceRecord["sourceId"], review: "unreviewed" });
    register.append({ ...validRecord, sourceId: "source-r" as SourceRecord["sourceId"], review: "rejected" });
    expect(Object.isFrozen(register.get("source-z" as SourceRecord["sourceId"]))).toBe(true);
    expect(register.listActive().map((record) => record.sourceId)).toEqual(["source-a2", "source-z"]);
    const restored = SourceRegister.fromJsonl(register.toJsonl());
    expect(restored.get("source-z" as SourceRecord["sourceId"])?.sha256).toBe(validRecord.sha256);
    expect(restored.get("source-z" as SourceRecord["sourceId"])?.review).toBe("accepted");
  });
});
