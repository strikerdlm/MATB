import { mkdirSync, writeFileSync } from "node:fs";
import { arch, cpus, platform, totalmem } from "node:os";
import { resolve } from "node:path";
import { performance } from "node:perf_hooks";
import { describe, expect, it } from "vitest";
import { ReplayGateway } from "../../packages/telemetry/test-support/index.js";

describe("accelerated long-duration replay", () => {
  it("preserves event order and retention across a synthetic 12-hour mission", async () => {
    const missionMinutes = 12 * 60;
    const missionStart = Date.parse("2026-08-10T00:00:00.000Z");
    const gateway = new ReplayGateway({ aircraftId: "aircraft-long-duration", now: () => "2026-08-10T12:00:00.000Z", maxDelayMs: 24 * 60 * 60 * 1_000 });
    const inputs = Array.from({ length: missionMinutes }, (_unused, minute) => ({
      eventId: `long-duration-${String(minute).padStart(4, "0")}`,
      aircraftId: "aircraft-long-duration",
      observedAtUtc: new Date(missionStart + minute * 60_000).toISOString(),
      motion: { headingDeg: minute % 360, groundSpeedKt: 85 },
      energy: { stateOfChargePercent: Math.max(20, 100 - minute / 9), reserveAtRecoveryPercent: 30 },
      sourcePackageIds: ["long-duration-telemetry-fixture"],
    }));
    const heapBeforeBytes = process.memoryUsage().heapUsed;
    const startedAt = performance.now();
    const records = await gateway.replay(inputs);
    const durationMs = performance.now() - startedAt;
    const heapAfterBytes = process.memoryUsage().heapUsed;

    expect(records).toHaveLength(missionMinutes);
    expect(records.every((record) => record.status === "accepted")).toBe(true);
    expect(gateway.acceptedEvents().map((event) => event.eventId)).toEqual(inputs.map((event) => event.eventId));
    expect(gateway.retentionRecords()).toHaveLength(missionMinutes);

    const directory = resolve(process.cwd(), "dist/reports/performance");
    mkdirSync(directory, { recursive: true });
    writeFileSync(resolve(directory, "long-duration.json"), `${JSON.stringify({
      schemaVersion: "1.0",
      environment: { node: process.version, platform: platform(), arch: arch(), cpuModel: cpus()[0]?.model ?? "unknown", logicalCpuCount: cpus().length, totalMemoryBytes: totalmem() },
      workload: { simulatedMissionHours: 12, sampleIntervalSeconds: 60, totalEvents: missionMinutes },
      measurement: { durationMs, heapBeforeBytes, heapAfterBytes, rejectedEvents: 0, orderErrors: 0 },
      assertionBasis: "correctness-only; no universal latency, memory, or endurance threshold asserted",
      limitations: ["Accelerated synthetic replay is not a 12-hour wall-clock soak test.", "Hardware-in-the-loop, storage endurance, thermal behavior, and tactical-network degradation remain institutional acceptance activities."],
    }, null, 2)}\n`, "utf8");
  });
});
