import { describe, expect, it } from "vitest";
import { SourceRegister } from "../src/index.js";
import type { SourceRecord, SupersessionRelationship } from "../src/types.js";

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
    register.append({ ...validRecord, sourceId: "source-a2" as SourceRecord["sourceId"], review: "accepted" });
    register.append({ ...validRecord, sourceId: "source-r" as SourceRecord["sourceId"], review: "rejected" });
    register.appendSupersession({ relationshipId: "rel-1", supersededSourceId: "source-z" as SourceRecord["sourceId"], replacementSourceId: "source-a2" as SourceRecord["sourceId"], recordedAtUtc: "2026-08-08T12:00:00Z" });
    expect(Object.isFrozen(register.get("source-z" as SourceRecord["sourceId"]))).toBe(true);
    expect(register.listActive().map((record) => record.sourceId)).toEqual(["source-a2"]);
    const restored = SourceRegister.fromJsonl(register.toJsonl());
    expect(restored.get("source-z" as SourceRecord["sourceId"])?.sha256).toBe(validRecord.sha256);
    expect(restored.get("source-z" as SourceRecord["sourceId"])?.review).toBe("accepted");
    expect(restored.listSupersessions()).toHaveLength(1);
    expect(restored.listActive().map((record) => record.sourceId)).toEqual(["source-a2"]);
  });

  it("rejects self, missing-target, duplicate, and conflicting supersession relationships", () => {
    const register = new SourceRegister(); register.append(validRecord);
    const relationship: SupersessionRelationship = { relationshipId: "rel-1", supersededSourceId: validRecord.sourceId, replacementSourceId: "missing" as SourceRecord["sourceId"], recordedAtUtc: "2026-08-08T12:00:00Z" };
    expect(() => register.appendSupersession(relationship)).toThrow("does not exist");
    register.append({ ...validRecord, sourceId: "source-b" as SourceRecord["sourceId"] });
    expect(() => register.appendSupersession({ ...relationship, replacementSourceId: validRecord.sourceId })).toThrow("itself");
    register.appendSupersession({ ...relationship, supersededSourceId: validRecord.sourceId, replacementSourceId: "source-b" as SourceRecord["sourceId"] });
    expect(() => register.appendSupersession({ ...relationship, relationshipId: "rel-2", replacementSourceId: "source-b" as SourceRecord["sourceId"] })).toThrow("already");
    expect(() => register.appendSupersession({ ...relationship, relationshipId: "rel-1", replacementSourceId: "source-b" as SourceRecord["sourceId"] })).toThrow("immutable");
    expect(() => register.appendSupersession({ ...relationship, relationshipId: "rel-bad", replacementSourceId: "source-b" as SourceRecord["sourceId"], recordedAtUtc: "not-a-time" })).toThrow("invalid fields");
    expect(() => register.appendSupersession({ ...relationship, relationshipId: "rel-bad", replacementSourceId: "source-b" as SourceRecord["sourceId"], supersededSourceId: "" as SourceRecord["sourceId"] })).toThrow("invalid fields");
    expect(() => register.appendSupersession(null as unknown as SupersessionRelationship)).toThrow("invalid fields");
    const unreviewed = new SourceRegister();
    unreviewed.append({ ...validRecord, review: "unreviewed" });
    unreviewed.append({ ...validRecord, sourceId: "source-c" as SourceRecord["sourceId"] });
    expect(() => unreviewed.appendSupersession({ ...relationship, replacementSourceId: "source-c" as SourceRecord["sourceId"] })).toThrow("accepted");
  });

  it("rejects malformed source validity timestamps", () => {
    expect(() => new SourceRegister().append({ ...validRecord, validFromUtc: "not-a-time" })).toThrow("valid UTC timestamp");
    expect(() => new SourceRegister().append({ ...validRecord, validUntilUtc: "2026-02-29T00:00:00Z" })).toThrow("valid UTC timestamp");
    expect(() => new SourceRegister().append({ ...validRecord, validFromUtc: "2026-08-09T00:00:00Z", validUntilUtc: "2026-08-08T00:00:00Z" })).toThrow("validity interval");
  });

  it("continues to honor legacy supersededBy values while relationships are authoritative", () => {
    const register = new SourceRegister();
    register.append({ ...validRecord, supersededBy: "legacy-replacement" as SourceRecord["sourceId"] });
    register.append({ ...validRecord, sourceId: "source-b" as SourceRecord["sourceId"] });
    expect(register.listActive().map((record) => record.sourceId)).toEqual(["source-b"]);
    expect(register.isSuperseded(validRecord.sourceId)).toBe(false);
  });
});
