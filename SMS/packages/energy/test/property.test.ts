import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { calculateMissionEnergy } from "../src/index.js";
import { parseBattery, parseEnergySegment } from "../src/types.js";
import { validEnergyInput } from "./fixtures.js";

describe("mission energy monotonicity", () => {
  it("does not improve reserve when payload increases", () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: 80 }), (additionalPayloadKg) => {
        const baseline = calculateMissionEnergy(validEnergyInput);
        const worsened = calculateMissionEnergy({
          ...validEnergyInput,
          payloadMassKg: validEnergyInput.payloadMassKg + additionalPayloadKg,
        });

        expect(worsened.contingencyReservePercent).toBeLessThanOrEqual(baseline.contingencyReservePercent);
        expect(worsened.predictedAtRecoveryPercent).toBeLessThanOrEqual(baseline.predictedAtRecoveryPercent);
      }),
    );
  });

  it("does not improve reserve with stronger adverse wind", () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: 80 }), (additionalWindKt) => {
        const baseline = calculateMissionEnergy(validEnergyInput);
        const worsened = calculateMissionEnergy({
          ...validEnergyInput,
          weather: { ...validEnergyInput.weather, windKt: validEnergyInput.weather.windKt + additionalWindKt },
        });

        expect(worsened.contingencyReservePercent).toBeLessThanOrEqual(baseline.contingencyReservePercent);
        expect(worsened.predictedAtRecoveryPercent).toBeLessThanOrEqual(baseline.predictedAtRecoveryPercent);
      }),
    );
  });

  it("does not improve reserve when battery health decreases", () => {
    fc.assert(
      fc.property(fc.integer({ min: 1, max: 98 }), (healthLossPercent) => {
        const baseline = calculateMissionEnergy(validEnergyInput);
        const worsened = calculateMissionEnergy({
          ...validEnergyInput,
          battery: parseBattery({
            ...validEnergyInput.battery,
            stateOfHealthPercent: Math.max(1, validEnergyInput.battery.stateOfHealthPercent - healthLossPercent),
          }),
        });

        expect(worsened.contingencyReservePercent).toBeLessThanOrEqual(baseline.contingencyReservePercent);
        expect(worsened.predictedAtRecoveryPercent).toBeLessThanOrEqual(baseline.predictedAtRecoveryPercent);
      }),
    );
  });

  it("does not improve reserve when a route segment gets longer", () => {
    fc.assert(
      fc.property(fc.integer({ min: 1, max: 30 }), (additionalMinutes) => {
        const baseline = calculateMissionEnergy(validEnergyInput);
        const longerCruise = parseEnergySegment({
          ...validEnergyInput.segments[1],
          durationS: (10 + additionalMinutes) * 60,
          durationMinutes: 10 + additionalMinutes,
        });
        const worsened = calculateMissionEnergy({
          ...validEnergyInput,
          segments: [validEnergyInput.segments[0], longerCruise, ...validEnergyInput.segments.slice(2)],
        });

        expect(worsened.contingencyReservePercent).toBeLessThanOrEqual(baseline.contingencyReservePercent);
        expect(worsened.predictedAtRecoveryPercent).toBeLessThanOrEqual(baseline.predictedAtRecoveryPercent);
      }),
    );
  });
});
