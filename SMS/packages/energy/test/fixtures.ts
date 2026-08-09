import { parseBattery, parseEnergySegment } from "../src/types.js";
import type { EnergyModelInput } from "../src/model.js";

const validBattery = parseBattery({
  serialNumber: "BAT-001",
  aircraftCompatibility: ["aircraft-1"],
  chemistry: "li-po",
  nominalCapacityWh: 100,
  nominalEnergyJ: 360_000,
  cycles: 25,
  ageDays: 40,
  stateOfChargePercent: 90,
  stateOfHealthPercent: 95,
  status: "released",
});

const segment = (id: string, kind: "climb" | "cruise" | "work" | "hold" | "return" | "diversion" | "contingency", distanceNm: number, durationS: number) => parseEnergySegment({
  id,
  kind,
  distanceNm,
  distanceM: distanceNm * 1852,
  durationS,
  expectedGroundspeedKt: 30,
  expectedGroundspeedMps: 30 * 0.5144444444444445,
});

export const validEnergyInput: EnergyModelInput = {
  aircraftId: "aircraft-1",
  battery: validBattery,
  segments: [
    segment("climb-1", "climb", 1, 300),
    segment("work-1", "work", 2, 600),
    segment("return-1", "return", 2, 600),
    segment("diversion-1", "diversion", 1, 300),
    segment("contingency-1", "contingency", 1, 300),
  ],
  weather: { windKt: 5, temperatureC: 20, densityAltitudeFt: 1_000 },
  payloadMassKg: 5,
  approvedReserve: {
    recoveryMinimumPercent: 20,
    diversionMinimumPercent: 10,
    contingencyMinimumPercent: 5,
    uncertaintyMethod: "approved-model",
    effectiveFromUtc: "2026-08-08T00:00:00Z",
  },
  modelVersion: "energy-fixture-1",
  performanceEvidenceRefs: ["energy-model-fixture-1"],
};
