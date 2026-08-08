import { canonicalJson } from "./hash.js";
import { assertSourceRecord } from "./index.js";
import type { SourceId, SourceRecord } from "./types.js";

/** An append-only in-memory registry of source revisions. */
export class SourceRegister {
  private readonly records = new Map<SourceId, SourceRecord>();

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

  /** Returns all non-rejected, non-superseded revisions in stable source-ID order. */
  listActive(): SourceRecord[] {
    return [...this.records.values()]
      .filter((record) => record.review !== "rejected" && record.review !== "superseded" && record.supersededBy === undefined)
      .sort((left, right) => left.sourceId.localeCompare(right.sourceId));
  }

  /** Stable JSONL representation, one canonical source record per line. */
  toJsonl(): string {
    return [...this.records.values()]
      .sort((left, right) => left.sourceId.localeCompare(right.sourceId))
      .map((record) => canonicalJson(record))
      .join("\n");
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
      register.append(value as SourceRecord);
    }
    return register;
  }
}

