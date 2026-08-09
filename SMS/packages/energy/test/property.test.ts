import { describe, expect, it } from "vitest";
import { calculateMissionEnergy, type EnergyModelInput } from "../src/model.js";
import { parseEnergySegment } from "../src/types.js";
import { validEnergyInput } from "./fixtures.js";

function resultFor(change: (input: EnergyModelInput) => EnergyModelInput) {
  return calculateMissionEnergy(change(validEnergyInput));
}

describe("mission energy monotonicity", () => {
  it("does not improve recovery reserve as payload increases", () => {
    const reserves = [0, 10, 20, 30].map((payloadMassKg) => resultFor((input) => ({ ...input, payloadMassKg })).predictedAtRecoveryPercent);
    for (let index = 1; index < reserves.length; index += 1) expect(reserves[index]).toBeLessThanOrEqual(reserves[index - 1]);
  });

  it("does not improve recovery reserve in stronger adverse wind", () => {
    const reserves = [0, 10, 20, 30].map((windKt) => resultFor((input) => ({ ...input, weather: { ...input.weather, windKt } })).predictedAtRecoveryPercent);
    for (let index = 1; index < reserves.length; index += 1) expect(reserves[index]).toBeLessThanOrEqual(reserves[index - 1]);
  });

  it("does not improve recovery reserve as battery health decreases", () => {
    const reserves = [100, 90, 80, 70].map((stateOfHealthPercent) => resultFor((input) => ({ ...input, battery: { ...input.battery, stateOfHealthPercent } })).predictedAtRecoveryPercent);
    for (let index = 1; index < reserves.length; index += 1) expect(reserves[index]).toBeLessThanOrEqual(reserves[index - 1]);
  });

  it("does not improve recovery reserve for a longer route", () => {
    const reserves = [1, 2, 3, 4].map((distanceNm) => resultFor((input) => ({
      ...input,
      segments: input.segments.map((segment, index) => parseEnergySegment({
        ...segment,
        distanceNm,
        distanceM: distanceNm * 1852,
        durationS: 300 + index * 120 + distanceNm * 60,
        durationMinutes: undefined,
      })),
    })).predictedAtRecoveryPercent);
    for (let index = 1; index < reserves.length; index += 1) expect(reserves[index]).toBeLessThanOrEqual(reserves[index - 1]);
  });
});
