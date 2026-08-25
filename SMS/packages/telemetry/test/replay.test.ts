import { describe, expect, it } from "vitest";
import {
  ReplayGateway,
  replayFixture,
} from "../test-support/index.js";
import type { CanonicalTelemetry } from "../src/index.js";

const base: CanonicalTelemetry = {
  eventId: "valid",
  aircraftId: "aircraft-1",
  observedAtUtc: "2026-08-09T18:00:00.000Z",
  sourcePackageIds: ["telemetry-package-1"],
};

describe("telemetry replay gateway", () => {
  it("deduplicates, rejects out-of-order records, and marks delayed records degraded", async () => {
    const gateway = new ReplayGateway({ aircraftId: "aircraft-1", now: () => "2026-08-09T18:00:10.000Z", maxDelayMs: 5_000 });
    const records = await gateway.replay([
      base,
      { ...base, eventId: "delayed", observedAtUtc: "2026-08-09T17:59:00.000Z" },
      { ...base, eventId: "malformed", position: { lat: 200, lon: 0 } },
      { ...base, eventId: "valid-2", observedAtUtc: "2026-08-09T18:00:01.000Z" },
      { ...base, eventId: "valid-2", observedAtUtc: "2026-08-09T18:00:02.000Z" },
    ]);

    expect(records.find((record) => record.eventId === "malformed")?.status).toBe("rejected");
    expect(records.find((record) => record.eventId === "delayed")?.status).toBe("degraded");
    expect(records.find((record) => record.eventId === "valid-2" && record.reason === "DUPLICATE_EVENT")?.status).toBe("rejected");
    expect(gateway.acceptedEvents().map((event) => event.eventId)).toEqual(["valid", "delayed", "valid-2"]);
  });

  it("retains a hash and one-year minimum record without raw imagery fields", async () => {
    const gateway = new ReplayGateway({ aircraftId: "aircraft-1", now: () => "2026-08-09T18:00:10.000Z" });
    await gateway.replay([base]);
    const retention = gateway.retentionRecords()[0]!;
    expect(retention.rawHash).toMatch(/^[a-f0-9]{64}$/);
    expect(Date.parse(retention.retainedUntilUtc) - Date.parse(base.observedAtUtc)).toBeGreaterThanOrEqual(365 * 24 * 60 * 60 * 1000);
    expect("image" in retention).toBe(false);
  });

  it("exports a deterministic fixture signature", async () => {
    const fixture = await replayFixture([base], { aircraftId: "aircraft-1" });
    expect(fixture.records).toHaveLength(1);
    expect(fixture.signature).toMatch(/^[a-f0-9]{64}$/);
  });
});
