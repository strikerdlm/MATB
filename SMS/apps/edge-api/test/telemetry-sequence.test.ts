import { describe, expect, it } from "vitest";
import { openDatabase } from "../src/db/migrate.js";
import { TelemetrySequenceRepository } from "../src/db/telemetry-sequence-repository.js";

describe("durable telemetry sequence compare-and-set", () => {
  it("allows at most one competing claimant and never regresses the stable adapter watermark", () => {
    const database = openDatabase(":memory:");
    try {
      const first = new TelemetrySequenceRepository(database);
      const second = new TelemetrySequenceRepository(database);
      const competing = [first.claim("adapter-1", "aircraft-1", 7), second.claim("adapter-1", "aircraft-1", 7)];
      expect(competing.filter(Boolean)).toHaveLength(1);
      expect(second.claim("adapter-1", "aircraft-1", 6)).toBe(false);
      expect(first.claim("adapter-1", "aircraft-1", 8)).toBe(true);
      expect(database.sql().prepare("SELECT adapter_id, aircraft_id, last_sequence FROM telemetry_sequence_watermarks").all()).toEqual([{ adapter_id: "adapter-1", aircraft_id: "aircraft-1", last_sequence: 8 }]);
    } finally {
      database.close();
    }
  });
});
