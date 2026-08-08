import { describe, expect, it } from "vitest";
import { assertSourceRecord } from "../src/index.js";
import type { SourceRecord } from "../src/types.js";

const validRecord: SourceRecord = {
  sourceId: "racae-94-enm2" as SourceRecord["sourceId"],
  title: "RACAE 94 Amendment 2",
  authority: "FAC",
  authorityRank: 1,
  canonicalUri: "https://example.gov/racae-94-enm2.pdf",
  localPath: "docs/regulations/original/racae-94-enm2.pdf",
  mediaType: "application/pdf",
  language: "es",
  retrievedAtUtc: "2026-08-08T12:00:00Z",
  sha256: "312458744b5e4f5097492d4b1c58b0e05229cc5e738058c757d4464e0f155976",
  sensitivity: "unclassified-controlled",
  licenseOrRestriction: "Official public source",
  review: "accepted",
};

describe("assertSourceRecord", () => {
  it("accepts a valid source record and returns it", () => {
    expect(assertSourceRecord(validRecord)).toBe(validRecord);
  });

  it.each([
    ["empty source ID", { sourceId: "" }],
    ["non-HTTPS canonical URI", { canonicalUri: "http://example.gov/source.pdf" }],
    ["invalid sensitivity", { sensitivity: "restricted" }],
  ])("rejects %s", (_description, override) => {
    expect(() => assertSourceRecord({ ...validRecord, ...override })).toThrow();
  });

  it("rejects records with missing required fields", () => {
    const { title: _title, ...missingTitle } = validRecord;
    expect(() => assertSourceRecord(missingTitle)).toThrow();
  });
});
