import type { EnergyModelInput } from "../src/model.js";
import { parseBattery, parseEnergySegment } from "../src/types.js";

const validBattery = parseBattery({
  serialNumber: "BAT-2026-001",
  aircraftCompatibility: ["uas-1"],
  chemistry: "li-po",
  nominalCapacityWh: 500,
  nominalEnergyJ: 1_800_000,
  cycles: 10,
  ageDays: 30,
  stateOfChargePercent: 90,
  stateOfHealthPercent: 98,
  status: "released",
});

const segment = (
  id: string,
  kind: "climb" | "cruise" | "work" | "hold" | "return" | "diversion" | "contingency",
  durationMinutes: number,
  payloadPowerW?: number,
) =>
  parseEnergySegment({
    id,
    kind,
    distanceNm: durationMinutes / 120,
    distanceM: (durationMinutes / 120) * 1852,
    durationS: durationMinutes * 60,
    durationMinutes,
    altitudeChangeFt: kind === "climb" ? 500 : 0,
    altitudeChangeM: kind === "climb" ? 152.4 : 0,
    expectedGroundspeedKt: 30,
    expectedGroundspeedMps: 30 * 0.5144444444444445,
    ...(payloadPowerW === undefined ? {} : { payloadPowerW }),
  });

export const validEnergyInput: EnergyModelInput = {
  aircraftId: "uas-1",
  battery: validBattery,
  segments: [
    segment("climb-1", "climb", 1),
    segment("cruise-1", "cruise", 10),
    segment("work-1", "work", 10, 20),
    segment("hold-1", "hold", 5),
    segment("return-1", "return", 8),
    segment("diversion-1", "diversion", 4),
    segment("contingency-1", "contingency", 5),
  ],
  weather: { windKt: 10, temperatureC: 25, densityAltitudeFt: 1_000 },
  payloadMassKg: 10,
  approvedReserve: {
    recoveryMinimumPercent: 15,
    diversionMinimumPercent: 10,
    contingencyMinimumPercent: 5,
    uncertaintyMethod: "approved-model",
    effectiveFromUtc: "2026-08-08T00:00:00Z",
  },
  modelVersion: "energy-model-v1",
  approvedPerformance: {
    basePowerWBySegment: {
      climb: 300,
      cruise: 180,
      work: 220,
      hold: 160,
      return: 190,
      diversion: 210,
      contingency: 180,
    },
    payloadPowerWPerKg: 2,
    climbEnergyPerMeterJ: 12,
    windPenaltyPercentPerKt: 0.5,
    referenceTemperatureC: 15,
    temperaturePenaltyPercentPerC: 0.3,
    referenceDensityAltitudeFt: 0,
    densityAltitudePenaltyPercentPer1000Ft: 0.1,
    uncertaintyPercent: 8,
    evidenceRefs: ["evidence:performance:energy-model-v1"],
  },
};

export { validBattery, segment };
