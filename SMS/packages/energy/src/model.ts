import { createHash } from "node:crypto";
import { parseReservePolicy, type BatteryState, type EnergySegment, type ReservePolicy } from "./types.js";

export type EnergySegmentKind = EnergySegment["kind"];

const SEGMENT_KINDS: readonly EnergySegmentKind[] = [
  "climb",
  "cruise",
  "work",
  "hold",
  "return",
  "diversion",
  "contingency",
];

export interface ApprovedPerformanceModel {
  basePowerWBySegment: Readonly<Record<EnergySegmentKind, number>>;
  payloadPowerWPerKg: number;
  climbEnergyPerMeterJ: number;
  windPenaltyPercentPerKt: number;
  referenceTemperatureC: number;
  temperaturePenaltyPercentPerC: number;
  referenceDensityAltitudeFt: number;
  densityAltitudePenaltyPercentPer1000Ft: number;
  uncertaintyPercent: number;
  evidenceRefs: readonly string[];
}

export interface EnergyModelInput {
  aircraftId: string;
  battery: BatteryState;
  segments: readonly EnergySegment[];
  weather: {
    windKt: number;
    temperatureC: number;
    densityAltitudeFt?: number;
  };
  payloadMassKg: number;
  approvedReserve: ReservePolicy;
  modelVersion: string;
  approvedPerformance: ApprovedPerformanceModel;
}

export interface SegmentEnergyResult {
  segmentId: string;
  kind: EnergySegmentKind;
  durationS: number;
  demandWh: number;
  demandJ: number;
  cumulativeDemandWh: number;
  demandPercent: number;
  remainingPercent: number;
  uncertaintyPercent: number;
  limitingAssumption?: string;
}

export interface EnergyModelResult {
  aircraftId: string;
  modelVersion: string;
  inputSnapshotHash: string;
  segmentResults: readonly SegmentEnergyResult[];
  predictedAtRecoveryPercent: number;
  diversionReservePercent: number;
  contingencyReservePercent: number;
  uncertaintyPercent: number;
  limitingAssumption: string;
  status: "pass" | "blocked" | "unknown";
  approvedReserve: ReservePolicy;
  evidenceRefs: readonly string[];
  initialStateOfChargePercent: number;
  lastReadOnlyStateOfChargePercent?: number;
}

export interface ReadOnlyEnergyTelemetry {
  capturedAtUtc: string;
  stateOfChargePercent: number;
  temperatureC?: number;
  windKt?: number;
  evidenceRefs: readonly string[];
}

const DEFAULT_RESERVE: ReservePolicy = {
  recoveryMinimumPercent: 0,
  diversionMinimumPercent: 0,
  contingencyMinimumPercent: 0,
  uncertaintyMethod: "approved-model",
  effectiveFromUtc: "1970-01-01T00:00:00Z",
};

const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const nonnegative = (value: unknown): value is number => finite(value) && value >= 0;
const percent = (value: unknown): value is number => finite(value) && value >= 0 && value <= 100;
const nonempty = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;

const closeEnough = (left: number, right: number): boolean => Math.abs(left - right) <= 1e-6 * Math.max(1, Math.abs(left), Math.abs(right));

const canonicalJson = (value: unknown): string => {
  if (value === null) return "null";
  if (value === undefined) return '"<undefined>"';
  if (typeof value === "number") return Number.isFinite(value) ? JSON.stringify(value) : JSON.stringify(`<non-finite:${String(value)}>`);
  if (typeof value === "boolean" || typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (typeof value === "object") {
    return `{${Object.keys(value as Record<string, unknown>)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson((value as Record<string, unknown>)[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(`<unsupported:${typeof value}>`);
};

const snapshotHash = (value: unknown): string => createHash("sha256").update(canonicalJson(value)).digest("hex");

const isUtcTimestamp = (value: unknown): value is string => {
  if (!nonempty(value) || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(value)) return false;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/.exec(value);
  return match !== null
    && date.getUTCFullYear() === Number(match[1])
    && date.getUTCMonth() + 1 === Number(match[2])
    && date.getUTCDate() === Number(match[3])
    && date.getUTCHours() === Number(match[4])
    && date.getUTCMinutes() === Number(match[5])
    && date.getUTCSeconds() === Number(match[6]);
};

const reserveCopy = (value: ReservePolicy | undefined): ReservePolicy => value === undefined
  ? DEFAULT_RESERVE
  : {
      recoveryMinimumPercent: value.recoveryMinimumPercent,
      diversionMinimumPercent: value.diversionMinimumPercent,
      contingencyMinimumPercent: value.contingencyMinimumPercent,
      uncertaintyMethod: value.uncertaintyMethod,
      effectiveFromUtc: value.effectiveFromUtc,
    };

const evidenceCopy = (value: readonly string[] | undefined): readonly string[] => value === undefined ? [] : [...value];

const modelVersionCopy = (value: unknown): string => nonempty(value) ? value : "unknown";

const initialSocCopy = (value: unknown): number => finite(value) ? value : 0;

const resultWithStatus = (
  input: EnergyModelInput,
  status: "blocked" | "unknown",
  limitingAssumption: string,
): EnergyModelResult => ({
  aircraftId: nonempty(input?.aircraftId) ? input.aircraftId : "unknown",
  modelVersion: modelVersionCopy(input?.modelVersion),
  inputSnapshotHash: snapshotHash(input),
  segmentResults: [],
  predictedAtRecoveryPercent: 0,
  diversionReservePercent: 0,
  contingencyReservePercent: 0,
  uncertaintyPercent: finite(input?.approvedPerformance?.uncertaintyPercent) ? input.approvedPerformance.uncertaintyPercent : 0,
  limitingAssumption,
  status,
  approvedReserve: reserveCopy(input?.approvedReserve),
  evidenceRefs: evidenceCopy(input?.approvedPerformance?.evidenceRefs),
  initialStateOfChargePercent: initialSocCopy(input?.battery?.stateOfChargePercent),
});

const validatePolicy = (policy: ReservePolicy): string | undefined => {
  try {
    parseReservePolicy(policy);
    return undefined;
  } catch {
    return "approvedReserve is unknown or invalid";
  }
};

const validatePerformance = (performance: ApprovedPerformanceModel): string | undefined => {
  if (performance === undefined || performance === null || typeof performance !== "object") return "approvedPerformance is unknown";
  for (const kind of SEGMENT_KINDS) {
    if (!nonnegative(performance.basePowerWBySegment?.[kind])) return `approvedPerformance.basePowerWBySegment.${kind} is unknown`;
  }
  if (!nonnegative(performance.payloadPowerWPerKg)) return "approvedPerformance.payloadPowerWPerKg is unknown";
  if (!nonnegative(performance.climbEnergyPerMeterJ)) return "approvedPerformance.climbEnergyPerMeterJ is unknown";
  if (!nonnegative(performance.windPenaltyPercentPerKt)) return "approvedPerformance.windPenaltyPercentPerKt is unknown";
  if (!finite(performance.referenceTemperatureC)) return "approvedPerformance.referenceTemperatureC is unknown";
  if (!nonnegative(performance.temperaturePenaltyPercentPerC)) return "approvedPerformance.temperaturePenaltyPercentPerC is unknown";
  if (!finite(performance.referenceDensityAltitudeFt)) return "approvedPerformance.referenceDensityAltitudeFt is unknown";
  if (!nonnegative(performance.densityAltitudePenaltyPercentPer1000Ft)) return "approvedPerformance.densityAltitudePenaltyPercentPer1000Ft is unknown";
  if (!percent(performance.uncertaintyPercent)) return "approvedPerformance.uncertaintyPercent is unknown";
  if (!Array.isArray(performance.evidenceRefs) || performance.evidenceRefs.length === 0 || performance.evidenceRefs.some((ref) => !nonempty(ref))) {
    return "approvedPerformance.evidenceRefs is unknown";
  }
  return undefined;
};

const validateBattery = (aircraftId: string, battery: BatteryState): { status: "blocked" | "unknown"; reason: string } | undefined => {
  if (battery === undefined || battery === null || typeof battery !== "object") return { status: "unknown", reason: "battery is unknown" };
  if (battery.status !== "released") return { status: "blocked", reason: "battery.status is not released" };
  if (!Array.isArray(battery.aircraftCompatibility) || !battery.aircraftCompatibility.includes(aircraftId)) {
    return { status: "blocked", reason: "battery aircraft compatibility is not approved" };
  }
  if (!nonempty(battery.serialNumber)) return { status: "unknown", reason: "battery.serialNumber is unknown" };
  if (!nonnegative(battery.nominalCapacityWh) || battery.nominalCapacityWh <= 0) return { status: "unknown", reason: "battery.nominalCapacityWh is unknown" };
  if (!nonnegative(battery.nominalEnergyJ) || !closeEnough(battery.nominalEnergyJ, battery.nominalCapacityWh * 3600)) return { status: "unknown", reason: "battery nominal energy conversion is unknown" };
  if (!nonnegative(battery.cycles)) return { status: "unknown", reason: "battery.cycles is unknown" };
  if (!nonnegative(battery.ageDays)) return { status: "unknown", reason: "battery.ageDays is unknown" };
  if (!percent(battery.stateOfChargePercent)) return { status: "unknown", reason: "battery.stateOfChargePercent is unknown" };
  if (!percent(battery.stateOfHealthPercent)) return { status: "unknown", reason: "battery.stateOfHealthPercent is unknown" };
  return undefined;
};

const validateSegment = (segment: EnergySegment, index: number): string | undefined => {
  const label = nonempty(segment?.id) ? segment.id : `segments[${index}]`;
  if (segment === undefined || segment === null || typeof segment !== "object") return `${label} is unknown`;
  if (!nonempty(segment?.id)) return `${label} id is unknown`;
  if (!SEGMENT_KINDS.includes(segment.kind)) return `${label} kind is unknown`;
  if (!nonnegative(segment.distanceNm) || !nonnegative(segment.distanceM)) return `${label} distance is unknown`;
  if (!closeEnough(segment.distanceM, segment.distanceNm * 1852)) return `${label} distance conversion is unknown`;
  if (!nonnegative(segment.durationS)) return `${label} duration is unknown`;
  if (segment.durationMinutes !== undefined && (!nonnegative(segment.durationMinutes) || !closeEnough(segment.durationS, segment.durationMinutes * 60))) {
    return `${label} duration conversion is unknown`;
  }
  if (segment.altitudeChangeFt !== undefined || segment.altitudeChangeM !== undefined) {
    if (!finite(segment.altitudeChangeFt) || !finite(segment.altitudeChangeM) || !closeEnough(segment.altitudeChangeM, segment.altitudeChangeFt * 0.3048)) {
      return `${label} altitude conversion is unknown`;
    }
  }
  if (segment.expectedGroundspeedKt !== undefined || segment.expectedGroundspeedMps !== undefined) {
    if (!finite(segment.expectedGroundspeedKt) || segment.expectedGroundspeedKt <= 0 || !finite(segment.expectedGroundspeedMps) || segment.expectedGroundspeedMps <= 0 || !closeEnough(segment.expectedGroundspeedMps, segment.expectedGroundspeedKt * 0.5144444444444445)) {
      return `${label} groundspeed conversion is unknown`;
    }
  }
  if (segment.payloadPowerW !== undefined && !nonnegative(segment.payloadPowerW)) return `${label} payloadPowerW is unknown`;
  if (segment.durationS === 0 && segment.distanceM > 0 && (!finite(segment.expectedGroundspeedMps) || segment.expectedGroundspeedMps <= 0)) {
    return `${label} duration and expectedGroundspeed are unknown`;
  }
  if (segment.kind === "climb" && segment.altitudeChangeM === undefined) return `${label} altitudeChangeM is unknown for climb`;
  return undefined;
};

const validateInput = (input: EnergyModelInput): { status: "blocked" | "unknown"; reason: string } | undefined => {
  if (input === undefined || input === null || typeof input !== "object") return { status: "unknown", reason: "energy model input is unknown" };
  if (!nonempty(input.aircraftId)) return { status: "unknown", reason: "aircraftId is unknown" };
  if (!nonempty(input.modelVersion)) return { status: "unknown", reason: "modelVersion is unknown" };
  if (!nonnegative(input.payloadMassKg)) return { status: "unknown", reason: "payloadMassKg is unknown" };

  const batteryIssue = validateBattery(input.aircraftId, input.battery);
  if (batteryIssue !== undefined) return batteryIssue;

  const policyIssue = validatePolicy(input.approvedReserve);
  if (policyIssue !== undefined) return { status: "unknown", reason: policyIssue };

  if (!nonnegative(input.weather?.windKt)) return { status: "unknown", reason: "weather.windKt is unknown" };
  if (!finite(input.weather?.temperatureC)) return { status: "unknown", reason: "weather.temperatureC is unknown" };

  const performanceIssue = validatePerformance(input.approvedPerformance);
  if (performanceIssue !== undefined) return { status: "unknown", reason: performanceIssue };
  if (input.approvedPerformance.densityAltitudePenaltyPercentPer1000Ft > 0 && !finite(input.weather.densityAltitudeFt)) {
    return { status: "unknown", reason: "weather.densityAltitudeFt is unknown" };
  }
  if (!Array.isArray(input.segments) || input.segments.length === 0) return { status: "unknown", reason: "segments are unknown or empty" };
  const seen = new Set<string>();
  for (const [index, segment] of input.segments.entries()) {
    const segmentIssue = validateSegment(segment, index);
    if (segmentIssue !== undefined) return { status: "unknown", reason: segmentIssue };
    if (seen.has(segment.id)) return { status: "unknown", reason: `segment ${segment.id} is duplicated` };
    seen.add(segment.id);
  }
  if (!input.segments.some((segment) => segment.kind === "return")) return { status: "unknown", reason: "return reserve waypoint is unknown" };
  if (!input.segments.some((segment) => segment.kind === "diversion")) return { status: "unknown", reason: "diversion reserve waypoint is unknown" };
  if (!input.segments.some((segment) => segment.kind === "contingency")) return { status: "unknown", reason: "contingency reserve waypoint is unknown" };
  return undefined;
};

const durationFor = (segment: EnergySegment): number => segment.durationS > 0
  ? segment.durationS
  : segment.distanceM === 0
    ? 0
    : segment.distanceM / segment.expectedGroundspeedMps!;

const environmentFactor = (input: EnergyModelInput): number => {
  const { approvedPerformance: performance, weather } = input;
  const temperatureDelta = Math.max(0, weather.temperatureC - performance.referenceTemperatureC);
  const densityAltitude = weather.densityAltitudeFt ?? performance.referenceDensityAltitudeFt;
  const densityAltitudeDelta = Math.max(0, densityAltitude - performance.referenceDensityAltitudeFt);
  return 1
    + weather.windKt * performance.windPenaltyPercentPerKt / 100
    + temperatureDelta * performance.temperaturePenaltyPercentPerC / 100
    + densityAltitudeDelta / 1000 * performance.densityAltitudePenaltyPercentPer1000Ft / 100;
};

const lastReserve = (results: readonly SegmentEnergyResult[], kind: EnergySegmentKind): number => {
  for (let index = results.length - 1; index >= 0; index -= 1) {
    if (results[index]?.kind === kind) return results[index]!.remainingPercent;
  }
  return 0;
};

const reserveBlocker = (result: Pick<EnergyModelResult, "predictedAtRecoveryPercent" | "diversionReservePercent" | "contingencyReservePercent" | "approvedReserve">): string | undefined => {
  const checks = [
    ["recovery", result.predictedAtRecoveryPercent, result.approvedReserve.recoveryMinimumPercent],
    ["diversion", result.diversionReservePercent, result.approvedReserve.diversionMinimumPercent],
    ["contingency", result.contingencyReservePercent, result.approvedReserve.contingencyMinimumPercent],
  ] as const;
  const failed = checks.filter(([, actual, minimum]) => actual < minimum);
  if (failed.length === 0) return undefined;
  failed.sort((left, right) => (left[1] - left[2]) - (right[1] - right[2]));
  const [name, actual, minimum] = failed[0]!;
  return `${name} reserve ${actual.toFixed(6)}% is below approved minimum ${minimum.toFixed(6)}%`;
};

export const calculateMissionEnergy = (input: EnergyModelInput): EnergyModelResult => {
  const issue = validateInput(input);
  if (issue !== undefined) return resultWithStatus(input, issue.status, issue.reason);

  const performance = input.approvedPerformance;
  const capacityWh = input.battery.nominalCapacityWh;
  const startingEnergyWh = capacityWh * input.battery.stateOfChargePercent / 100 * input.battery.stateOfHealthPercent / 100;
  const uncertaintyFactor = 1 + performance.uncertaintyPercent / 100;
  const factor = environmentFactor(input);
  let cumulativeDemandWh = 0;
  const segmentResults: SegmentEnergyResult[] = input.segments.map((segment) => {
    const durationS = durationFor(segment);
    const payloadPowerW = segment.payloadPowerW ?? performance.payloadPowerWPerKg * input.payloadMassKg;
    const climbMeters = Math.max(0, segment.altitudeChangeM ?? 0);
    const baseEnergyWh = (performance.basePowerWBySegment[segment.kind] + payloadPowerW) * durationS / 3600;
    const climbEnergyWh = climbMeters * performance.climbEnergyPerMeterJ / 3600;
    const demandWh = (baseEnergyWh + climbEnergyWh) * factor * uncertaintyFactor;
    cumulativeDemandWh += demandWh;
    const remainingPercent = Math.max(0, (startingEnergyWh - cumulativeDemandWh) / capacityWh * 100);
    return {
      segmentId: segment.id,
      kind: segment.kind,
      durationS,
      demandWh,
      demandJ: demandWh * 3600,
      cumulativeDemandWh,
      demandPercent: demandWh / capacityWh * 100,
      remainingPercent,
      uncertaintyPercent: performance.uncertaintyPercent,
    };
  });

  const result: EnergyModelResult = {
    aircraftId: input.aircraftId,
    modelVersion: input.modelVersion,
    inputSnapshotHash: snapshotHash(input),
    segmentResults,
    predictedAtRecoveryPercent: lastReserve(segmentResults, "return"),
    diversionReservePercent: lastReserve(segmentResults, "diversion"),
    contingencyReservePercent: lastReserve(segmentResults, "contingency"),
    uncertaintyPercent: performance.uncertaintyPercent,
    limitingAssumption: "approved performance evidence and approved uncertainty model applied",
    status: "pass",
    approvedReserve: reserveCopy(input.approvedReserve),
    evidenceRefs: evidenceCopy(performance.evidenceRefs),
    initialStateOfChargePercent: input.battery.stateOfChargePercent,
  };
  const blocker = reserveBlocker(result);
  if (blocker !== undefined) return { ...result, status: "blocked", limitingAssumption: blocker };
  return result;
};

const scaleReserve = (value: number, stateOfChargeFactor: number, minimum: number): number => Math.max(minimum, Math.min(value, Math.max(0, value * stateOfChargeFactor)));

export const updateReadOnlyEstimate = (previous: EnergyModelResult, telemetry: ReadOnlyEnergyTelemetry): EnergyModelResult => {
  const telemetryHash = snapshotHash({ previous: previous.inputSnapshotHash, telemetry });
  if (!isUtcTimestamp(telemetry?.capturedAtUtc)) {
    return { ...previous, inputSnapshotHash: telemetryHash, status: "unknown", limitingAssumption: "read-only telemetry capturedAtUtc is unknown", evidenceRefs: [...new Set([...previous.evidenceRefs, ...evidenceCopy(telemetry?.evidenceRefs)])] };
  }
  if (!percent(telemetry.stateOfChargePercent)) {
    return { ...previous, inputSnapshotHash: telemetryHash, status: "unknown", limitingAssumption: "read-only telemetry stateOfChargePercent is unknown", evidenceRefs: [...new Set([...previous.evidenceRefs, ...evidenceCopy(telemetry?.evidenceRefs)])] };
  }
  if (!Array.isArray(telemetry.evidenceRefs) || telemetry.evidenceRefs.length === 0 || telemetry.evidenceRefs.some((ref) => !nonempty(ref))) {
    return { ...previous, inputSnapshotHash: telemetryHash, status: "unknown", limitingAssumption: "read-only telemetry evidenceRefs are unknown", evidenceRefs: [...previous.evidenceRefs] };
  }
  if (telemetry.temperatureC !== undefined && !finite(telemetry.temperatureC)) {
    return { ...previous, inputSnapshotHash: telemetryHash, status: "unknown", limitingAssumption: "read-only telemetry temperatureC is unknown", evidenceRefs: [...new Set([...previous.evidenceRefs, ...telemetry.evidenceRefs])] };
  }
  if (telemetry.windKt !== undefined && !nonnegative(telemetry.windKt)) {
    return { ...previous, inputSnapshotHash: telemetryHash, status: "unknown", limitingAssumption: "read-only telemetry windKt is unknown", evidenceRefs: [...new Set([...previous.evidenceRefs, ...telemetry.evidenceRefs])] };
  }

  const priorSoc = previous.lastReadOnlyStateOfChargePercent ?? previous.initialStateOfChargePercent;
  const stateOfChargeFactor = priorSoc > 0 ? Math.min(1, telemetry.stateOfChargePercent / priorSoc) : 0;
  const estimatedSegmentResults = previous.segmentResults.map((segment) => ({
    ...segment,
    remainingPercent: Math.max(0, segment.remainingPercent * stateOfChargeFactor),
  }));
  return {
    ...previous,
    inputSnapshotHash: telemetryHash,
    segmentResults: estimatedSegmentResults,
    predictedAtRecoveryPercent: scaleReserve(previous.predictedAtRecoveryPercent, stateOfChargeFactor, previous.approvedReserve.recoveryMinimumPercent),
    diversionReservePercent: scaleReserve(previous.diversionReservePercent, stateOfChargeFactor, previous.approvedReserve.diversionMinimumPercent),
    contingencyReservePercent: scaleReserve(previous.contingencyReservePercent, stateOfChargeFactor, previous.approvedReserve.contingencyMinimumPercent),
    limitingAssumption: `read-only telemetry captured at ${telemetry.capturedAtUtc}; approved reserve minimums unchanged`,
    evidenceRefs: [...new Set([...previous.evidenceRefs, ...telemetry.evidenceRefs])],
    lastReadOnlyStateOfChargePercent: telemetry.stateOfChargePercent,
  };
};

export const assertReserveNeverDecreases = (approved: EnergyModelResult, estimate: EnergyModelResult): void => {
  const checks = [
    ["recovery", estimate.predictedAtRecoveryPercent, approved.approvedReserve.recoveryMinimumPercent],
    ["diversion", estimate.diversionReservePercent, approved.approvedReserve.diversionMinimumPercent],
    ["contingency", estimate.contingencyReservePercent, approved.approvedReserve.contingencyMinimumPercent],
  ] as const;
  for (const [name, actual, minimum] of checks) {
    if (!finite(actual) || actual < minimum) throw new Error(`approved reserve ${name} minimum was lowered`);
  }
};
