import { describe, expect, it } from "vitest";
import {
  assertReserveNeverDecreases,
  calculateMissionEnergy,
  updateReadOnlyEstimate,
  type EnergyModelInput,
  type ReadOnlyEnergyTelemetry,
} from "../src/index.js";
import { parseBattery, parseEnergySegment } from "../src/types.js";
import { validEnergyInput } from "./fixtures.js";

describe("deterministic mission energy model", () => {
  it("reports demand and reserve at every waypoint", () => {
    const result = calculateMissionEnergy(validEnergyInput);

    expect(result.status).toBe("pass");
    expect(result.segmentResults).toHaveLength(validEnergyInput.segments.length);
    expect(result.segmentResults.every((item) => item.demandWh > 0)).toBe(true);
    expect(result.segmentResults.every((item) => Number.isFinite(item.remainingPercent))).toBe(true);
    expect(result.predictedAtRecoveryPercent).toBeGreaterThanOrEqual(0);
    expect(result.contingencyReservePercent).toBeGreaterThan(0);
    expect(result.modelVersion).toBe(validEnergyInput.modelVersion);
    expect(result.inputSnapshotHash).toMatch(/^[a-f0-9]{64}$/);
    expect(result.uncertaintyPercent).toBe(8);
    expect(result.limitingAssumption).toContain("approved");
  });

  it.each([
    ["payloadMassKg", { payloadMassKg: Number.NaN }, "payloadMassKg"],
    ["weather.windKt", { weather: { ...validEnergyInput.weather, windKt: Number.NaN } }, "weather.windKt"],
    ["battery.stateOfHealthPercent", { battery: { ...validEnergyInput.battery, stateOfHealthPercent: Number.NaN } }, "battery.stateOfHealthPercent"],
    ["approved performance evidence", { approvedPerformance: { ...validEnergyInput.approvedPerformance, evidenceRefs: [] } }, "approvedPerformance.evidenceRefs"],
  ])("returns unknown when %s is not evidenced", (_name, change, limitingAssumption) => {
    const result = calculateMissionEnergy({ ...validEnergyInput, ...change } as EnergyModelInput);

    expect(result.status).toBe("unknown");
    expect(result.limitingAssumption).toContain(limitingAssumption);
  });

  it("blocks a battery that is not released for the aircraft", () => {
    const result = calculateMissionEnergy({
      ...validEnergyInput,
      battery: { ...validEnergyInput.battery, status: "restricted" },
    });

    expect(result.status).toBe("blocked");
    expect(result.limitingAssumption).toContain("battery.status");
  });

  it("derives missing duration from normalized distance and groundspeed", () => {
    const derived = parseEnergySegment({
      id: "cruise-derived",
      kind: "cruise",
      distanceNm: 1,
      distanceM: 1852,
      durationS: 0,
      expectedGroundspeedKt: 30,
      expectedGroundspeedMps: 30 * 0.5144444444444445,
    });
    const result = calculateMissionEnergy({
      ...validEnergyInput,
      segments: [
        derived,
        validEnergyInput.segments[4]!,
        validEnergyInput.segments[5]!,
        validEnergyInput.segments[6]!,
      ],
    });

    expect(result.status).toBe("pass");
    expect(result.segmentResults[0]?.durationS).toBeCloseTo(1852 / (30 * 0.5144444444444445));
  });

  it("returns unknown instead of assuming a duration for a nonzero route", () => {
    const result = calculateMissionEnergy({
      ...validEnergyInput,
      segments: [
        parseEnergySegment({ id: "cruise-unknown", kind: "cruise", distanceNm: 1, distanceM: 1852, durationS: 0 }),
        ...validEnergyInput.segments.slice(4),
      ],
    });

    expect(result.status).toBe("unknown");
    expect(result.limitingAssumption).toContain("cruise-unknown");
  });

  it("keeps read-only telemetry estimates above the approved reserve floor", () => {
    const approved = calculateMissionEnergy(validEnergyInput);
    const telemetry: ReadOnlyEnergyTelemetry = {
      capturedAtUtc: "2026-08-08T01:00:00Z",
      stateOfChargePercent: 1,
      temperatureC: 40,
      windKt: 30,
      evidenceRefs: ["telemetry:read-only:2026-08-08T01:00:00Z"],
    };
    const estimate = updateReadOnlyEstimate(approved, telemetry);

    expect(estimate.contingencyReservePercent).toBe(approved.approvedReserve.contingencyMinimumPercent);
    expect(estimate.diversionReservePercent).toBe(approved.approvedReserve.diversionMinimumPercent);
    expect(() => assertReserveNeverDecreases(approved, estimate)).not.toThrow();
  });

  it("rejects an estimate below any approved reserve minimum", () => {
    const approved = calculateMissionEnergy(validEnergyInput);
    const estimate = {
      ...approved,
      contingencyReservePercent: approved.approvedReserve.contingencyMinimumPercent - 0.001,
    };

    expect(() => assertReserveNeverDecreases(approved, estimate)).toThrow("approved reserve");
  });
});
