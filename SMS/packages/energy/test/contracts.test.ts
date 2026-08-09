import { describe, expect, it } from "vitest";
import { altitudeChangeFeetToMeters, feetToMeters, knotsToMetersPerSecond, nauticalMilesToMeters, parseBattery, parseEnergySegment, parseReservePolicy, wattHoursToJoules } from "../src/types.js";

const validBattery = { serialNumber: "BAT-2026-001", aircraftCompatibility: ["uas-1"], chemistry: "li-po", nominalCapacityWh: 500, nominalEnergyJ: 1800000, cycles: 10, ageDays: 30, stateOfChargePercent: 90, stateOfHealthPercent: 98, status: "released" };
describe("energy contracts", () => {
  it("rejects a battery with negative cycles or state of health above 100%", () => {
    expect(() => parseBattery({ ...validBattery, cycles: -1 })).toThrow();
    expect(() => parseBattery({ ...validBattery, stateOfHealthPercent: 101 })).toThrow();
    expect(parseBattery(validBattery).nominalCapacityWh).toBe(500);
  });
  it("rejects non-finite/negative energy and local timestamps", () => {
    expect(() => parseBattery({ ...validBattery, nominalCapacityWh: Infinity })).toThrow();
    expect(() => parseEnergySegment({ id: "seg-1", kind: "cruise", distanceNm: -1, distanceM: 0, durationS: 1 })).toThrow();
    expect(parseEnergySegment({ id: "seg-1", kind: "cruise", distanceNm: 1, distanceM: 1852, durationS: 60 }).distanceM).toBe(1852);
    expect(() => parseReservePolicy({ recoveryMinimumPercent: 20, diversionMinimumPercent: 10, contingencyMinimumPercent: 5, uncertaintyMethod: "approved-model", effectiveFromUtc: "2026-08-08T00:00:00-05:00" })).toThrow();
  });
  it("requires normalized SI dimensions and preserves raw telemetry", () => {
    expect(() => parseBattery({ ...validBattery, nominalEnergyJ: undefined })).toThrow();
    expect(parseBattery({ ...validBattery, nominalEnergyJ: 1800000, cellImbalanceMv: 10, cellImbalanceV: 0.01, internalResistanceMohm: 5, internalResistanceOhm: 0.005, temperatureC: 25, temperatureK: 298.15, rawTelemetryValues: { capacityWh: "500" } }).rawTelemetryValues).toEqual({ capacityWh: "500" });
    expect(() => parseEnergySegment({ id: "seg-1", kind: "cruise", distanceNm: 1, durationS: 60 })).toThrow();
    expect(() => parseBattery({ ...validBattery, nominalEnergyJ: 1 })).toThrow("watt-hours");
    expect(() => parseEnergySegment({ id: "seg-1", kind: "cruise", distanceNm: 1, distanceM: 1, durationS: 60 })).toThrow("nautical miles");
  });
  it("provides deterministic display-to-SI conversions", () => {
    expect(nauticalMilesToMeters(1)).toBe(1852); expect(feetToMeters(1)).toBeCloseTo(0.3048); expect(knotsToMetersPerSecond(1)).toBeCloseTo(0.514444); expect(wattHoursToJoules(1)).toBe(3600);
    expect(() => nauticalMilesToMeters(-1)).toThrow(); expect(() => feetToMeters(Number.NaN)).toThrow(); expect(() => knotsToMetersPerSecond(-1)).toThrow(); expect(() => wattHoursToJoules(Infinity)).toThrow();
    expect(altitudeChangeFeetToMeters(-100)).toBeCloseTo(-30.48);
  });
  it("requires matching altitude and groundspeed display/SI pairs", () => {
    const base = { id: "seg-1", kind: "cruise", distanceNm: 1, distanceM: 1852, durationS: 60 };
    expect(parseEnergySegment({ ...base, altitudeChangeFt: 100, altitudeChangeM: 30.48, expectedGroundspeedKt: 10, expectedGroundspeedMps: 5.144444444444445 }).id).toBe("seg-1");
    expect(() => parseEnergySegment({ ...base, altitudeChangeFt: 100 })).toThrow("altitude");
    expect(() => parseEnergySegment({ ...base, expectedGroundspeedMps: 5 })).toThrow("groundspeed");
    expect(() => parseEnergySegment({ ...base, altitudeChangeFt: 100, altitudeChangeM: 1 })).toThrow("feet");
    expect(parseEnergySegment({ ...base, altitudeChangeFt: -100, altitudeChangeM: -30.48 }).altitudeChangeM).toBeCloseTo(-30.48);
    expect(() => parseEnergySegment({ ...base, altitudeChangeFt: -100, altitudeChangeM: -1 })).toThrow("feet");
  });
});
