import { mkdirSync, writeFileSync } from "node:fs";
import { arch, cpus, platform, totalmem } from "node:os";
import { resolve } from "node:path";
import { performance } from "node:perf_hooks";
import { describe, expect, it } from "vitest";
import { AuditLedger } from "../../apps/edge-api/src/audit/ledger.js";
import { ReplayGateway } from "../../packages/telemetry/test-support/index.js";

const AIRCRAFT_COUNT = 12;
const EVENTS_PER_AIRCRAFT = 240;

function writeMetrics(name: string, metrics: Record<string, unknown>): void {
  const directory = resolve(process.cwd(), "dist/reports/performance");
  mkdirSync(directory, { recursive: true });
  writeFileSync(resolve(directory, `${name}.json`), `${JSON.stringify({
    schemaVersion: "1.0",
    environment: { node: process.version, platform: platform(), arch: arch(), cpuModel: cpus()[0]?.model ?? "unknown", logicalCpuCount: cpus().length, totalMemoryBytes: totalmem() },
    ...metrics,
  }, null, 2)}\n`, "utf8");
}

describe("configured tactical multi-aircraft workload", () => {
  it("replays ordered telemetry for every aircraft without rejection or cross-aircraft mixing", async () => {
    const startedAt = performance.now();
    const results = await Promise.all(Array.from({ length: AIRCRAFT_COUNT }, async (_unused, aircraftIndex) => {
      const aircraftId = `aircraft-${String(aircraftIndex + 1).padStart(2, "0")}`;
      const gateway = new ReplayGateway({ aircraftId, now: () => "2026-08-10T12:10:00.000Z", maxDelayMs: 3_600_000 });
      const events = Array.from({ length: EVENTS_PER_AIRCRAFT }, (_event, sequence) => ({
        eventId: `${aircraftId}-event-${String(sequence).padStart(4, "0")}`,
        aircraftId,
        observedAtUtc: new Date(Date.parse("2026-08-10T12:00:00.000Z") + sequence * 1_000).toISOString(),
        position: { lat: 4.5 + aircraftIndex / 100, lon: -74.1, altitudeMslM: 1_000 + sequence },
        sourcePackageIds: ["performance-telemetry-fixture"],
      }));
      return { aircraftId, records: await gateway.replay(events), accepted: gateway.acceptedEvents() };
    }));
    const durationMs = performance.now() - startedAt;

    for (const result of results) {
      expect(result.records).toHaveLength(EVENTS_PER_AIRCRAFT);
      expect(result.records.every((record) => record.status === "accepted")).toBe(true);
      expect(result.accepted.every((event) => event.aircraftId === result.aircraftId)).toBe(true);
      expect(result.accepted.map((event) => event.eventId)).toEqual(
        Array.from({ length: EVENTS_PER_AIRCRAFT }, (_event, sequence) => `${result.aircraftId}-event-${String(sequence).padStart(4, "0")}`),
      );
    }
    writeMetrics("multi-aircraft", {
      workload: { aircraftCount: AIRCRAFT_COUNT, eventsPerAircraft: EVENTS_PER_AIRCRAFT, totalEvents: AIRCRAFT_COUNT * EVENTS_PER_AIRCRAFT },
      measurement: { durationMs, rejectedEvents: 0, mixedAircraftEvents: 0 },
      assertionBasis: "correctness-only; no universal latency or throughput threshold asserted",
      limitations: ["Synthetic in-process replay; hardware-in-the-loop and tactical-network load remain institutional acceptance activities."],
    });
  });

  it("serializes concurrent audit writes without gaps or hash-chain corruption", async () => {
    const ledger = new AuditLedger({ now: () => "2026-08-10T12:00:00.000Z" });
    const writeCount = 240;
    const startedAt = performance.now();
    const events = await Promise.all(Array.from({ length: writeCount }, (_unused, sequence) => ledger.append({
      eventId: `concurrent-audit-${String(sequence).padStart(4, "0")}`,
      type: "performance.concurrent-write",
      actorUserId: `operator-${sequence % AIRCRAFT_COUNT}`,
      missionRevisionId: `mission-${sequence % AIRCRAFT_COUNT}:r0`,
      action: "record",
      reason: "performance verification fixture",
      payload: { submittedSequence: sequence },
    })));
    const durationMs = performance.now() - startedAt;

    expect(events.map((event) => event.sequence)).toEqual(Array.from({ length: writeCount }, (_unused, sequence) => sequence));
    await expect(ledger.verifyAuditChain()).resolves.toEqual({ ok: true, checkedEvents: writeCount });
    writeMetrics("concurrent-audit", {
      workload: { concurrentSubmissions: writeCount, missionCount: AIRCRAFT_COUNT },
      measurement: { durationMs, droppedWrites: 0, sequenceGaps: 0, hashChainBreaks: 0 },
      assertionBasis: "correctness-only; no universal latency or throughput threshold asserted",
      limitations: ["In-memory ledger fixture; receiving-node SQLite and storage endurance must be measured on approved hardware."],
    });
  });
});
