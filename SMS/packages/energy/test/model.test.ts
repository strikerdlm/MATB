import { describe, expect, it } from "vitest";
import {
  assertReserveNeverDecreases,
  calculateMissionEnergy,
  updateReadOnlyEstimate,
  type EnergyModelInput,
} from "../src/model.js";
import type { EnergyModelResult } from "../src/model.js";
import { validEnergyInput } from "./fixtures.js";

describe("mission energy model", () => {
  it("reports predicted energy at every waypoint and reserve segments", () => {
    const result = calculateMissionEnergy(validEnergyInput);
    expect(result.segmentResults).toHaveLength(validEnergyInput.segments.length);
    expect(result.segmentResults.every(({ segmentId }) => segmentId.length > 0)).toBe(true);
    expect(result.predictedAtRecoveryPercent).toBeGreaterThanOrEqual(0);
    expect(result.contingencyReservePercent).toBeGreaterThan(0);
    expect(result.inputSnapshotHash).toMatch(/^[a-f0-9]{64}$/);
    expect(result.evidenceRefs).toContain("energy-model-fixture-1");
  });

  it("returns unknown for missing payload, wind, battery-health, or model evidence", () => {
    const variants: readonly EnergyModelInput[] = [
      { ...validEnergyInput, payloadMassKg: Number.NaN },
      { ...validEnergyInput, weather: { ...validEnergyInput.weather, windKt: Number.NaN } },
      { ...validEnergyInput, battery: { ...validEnergyInput.battery, stateOfHealthPercent: Number.NaN } },
      { ...validEnergyInput, performanceEvidenceRefs: [] },
    ];
    for (const input of variants) expect(calculateMissionEnergy(input).status).toBe("unknown");
  });

  it("does not let read-only telemetry lower approved reserve floors", () => {
    const approved = calculateMissionEnergy(validEnergyInput);
    expect(approved.status).toBe("pass");
    const telemetryEstimate = updateReadOnlyEstimate(approved, {
      stateOfChargePercent: 75,
      stateOfHealthPercent: 90,
      windKt: 10,
      temperatureC: 18,
    });
    expect(telemetryEstimate.approvedReserve.recoveryMinimumPercent)
      .toBe(approved.approvedReserve.recoveryMinimumPercent);
    expect(telemetryEstimate.approvedReserve.contingencyMinimumPercent)
      .toBe(approved.approvedReserve.contingencyMinimumPercent);

    const belowReserve = {
      ...approved,
      predictedAtRecoveryPercent: approved.approvedReserve.recoveryMinimumPercent - 1,
    } as EnergyModelResult;
    expect(() => assertReserveNeverDecreases(approved, belowReserve)).toThrow("approved reserve");
  });
});
