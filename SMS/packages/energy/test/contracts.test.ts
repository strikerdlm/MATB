import { describe, expect, it } from "vitest";
import { parseBattery, parseEnergySegment, parseReservePolicy } from "../src/types.js";

const validBattery = { serialNumber: "BAT-2026-001", aircraftCompatibility: ["uas-1"], chemistry: "li-po", nominalCapacityWh: 500, cycles: 10, ageDays: 30, stateOfChargePercent: 90, stateOfHealthPercent: 98, status: "released" };
describe("energy contracts", () => {
  it("rejects a battery with negative cycles or state of health above 100%", () => {
    expect(() => parseBattery({ ...validBattery, cycles: -1 })).toThrow();
    expect(() => parseBattery({ ...validBattery, stateOfHealthPercent: 101 })).toThrow();
    expect(parseBattery(validBattery).nominalCapacityWh).toBe(500);
  });
  it("rejects non-finite/negative energy and local timestamps", () => {
    expect(() => parseBattery({ ...validBattery, nominalCapacityWh: Infinity })).toThrow();
    expect(() => parseEnergySegment({ id: "seg-1", kind: "cruise", distanceNm: -1 })).toThrow();
    expect(() => parseReservePolicy({ recoveryMinimumPercent: 20, diversionMinimumPercent: 10, contingencyMinimumPercent: 5, uncertaintyMethod: "approved-model", effectiveFromUtc: "2026-08-08T00:00:00-05:00" })).toThrow();
  });
});
