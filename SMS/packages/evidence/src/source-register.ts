import { canonicalJson } from "./hash.js";
import { assertSourceRecord } from "./source-validation.js";
import { isUtcTimestamp } from "./source-validation.js";
import type { SourceId, SourceRecord, SupersessionRelationship } from "./types.js";

/** An append-only in-memory registry of source revisions. */
export class SourceRegister {
  private readonly records = new Map<SourceId, SourceRecord>();
  private readonly relationships = new Map<string, SupersessionRelationship>();

  append(record: SourceRecord): void {
    assertSourceRecord(record);
    if (this.records.has(record.sourceId)) {
      throw new Error(`Source ${record.sourceId} is immutable and cannot be rewritten`);
    }
    this.records.set(record.sourceId, Object.freeze({ ...record }));
  }

  get(sourceId: SourceId): SourceRecord | undefined {
    return this.records.get(sourceId);
  }

  appendSupersession(relationship: SupersessionRelationship): void {
    if (typeof relationship.relationshipId !== "string" || relationship.relationshipId.trim() === "" || typeof relationship.supersededSourceId !== "string" || relationship.supersededSourceId.trim() === "" || typeof relationship.replacementSourceId !== "string" || relationship.replacementSourceId.trim() === "" || !isUtcTimestamp(relationship.recordedAtUtc)) throw new Error("Supersession relationship has invalid fields");
    if (relationship.supersededSourceId === relationship.replacementSourceId) throw new Error("Supersession relationship cannot target itself");
    if (!this.records.has(relationship.supersededSourceId) || !this.records.has(relationship.replacementSourceId)) throw new Error("Supersession relationship target source does not exist");
    if (this.relationships.has(relationship.relationshipId)) throw new Error("Supersession relationship is immutable");
    if ([...this.relationships.values()].some((item) => item.supersededSourceId === relationship.supersededSourceId)) throw new Error("Source already has a supersession relationship");
    if (this.records.get(relationship.supersededSourceId)?.review === "rejected" || this.records.get(relationship.replacementSourceId)?.review !== "accepted") throw new Error("Supersession sources have incoherent review status");
    if (this.isSuperseded(relationship.replacementSourceId)) throw new Error("Supersession replacement is already superseded");
    this.relationships.set(relationship.relationshipId, Object.freeze({ ...relationship }));
  }

  listSupersessions(): SupersessionRelationship[] { return [...this.relationships.values()].sort((a, b) => a.relationshipId.localeCompare(b.relationshipId)); }
  isSuperseded(sourceId: SourceId): boolean { return [...this.relationships.values()].some((item) => item.supersededSourceId === sourceId); }

  /** Returns all non-rejected, non-superseded revisions in stable source-ID order. */
  listActive(): SourceRecord[] {
    return [...this.records.values()]
      .filter((record) => record.review !== "rejected" && record.review !== "superseded" && record.supersededBy === undefined && !this.isSuperseded(record.sourceId))
      .sort((left, right) => left.sourceId.localeCompare(right.sourceId));
  }

  /** Stable JSONL representation, one canonical source record per line. */
  toJsonl(): string {
    const sources = [...this.records.values()]
      .sort((left, right) => left.sourceId.localeCompare(right.sourceId))
      .map((record) => canonicalJson(record));
    return [...sources, ...this.listSupersessions().map((relationship) => canonicalJson({ _type: "supersession", ...relationship }))].join("\n");
  }

  static fromJsonl(serialized: string): SourceRegister {
    const register = new SourceRegister();
    if (serialized.trim() === "") return register;
    for (const [index, line] of serialized.split(/\r?\n/).entries()) {
      if (line.trim() === "") continue;
      let value: unknown;
      try {
        value = JSON.parse(line);
      } catch {
        throw new Error(`Invalid source register JSONL at line ${index + 1}`);
      }
      if (value !== null && typeof value === "object" && (value as Record<string, unknown>)._type === "supersession") register.appendSupersession(value as SupersessionRelationship);
      else register.append(value as SourceRecord);
    }
    return register;
  }
}
