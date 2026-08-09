import { createHash } from "node:crypto";
import type { BatteryState, EnergySegment, ReservePolicy } from "./types.js";

export interface EnergyPerformanceEvidence {
  basePowerWByKind?: Partial<Record<EnergySegment["kind"], number>>;
  energyPerNmWh?: number;
  payloadPowerPerKgW?: number;
  uncertaintyPercent?: number;
  evidenceRefs?: readonly string[];
}

export interface EnergyModelInput {
  aircraftId: string;
  battery: BatteryState;
  segments: readonly EnergySegment[];
  weather: { windKt: number; temperatureC: number; densityAltitudeFt?: number };
  payloadMassKg: number;
  approvedReserve: ReservePolicy;
  modelVersion: string;
  /** Empty evidence is explicitly unknown; omission falls back to the versioned model identifier. */
  performanceEvidenceRefs?: readonly string[];
  performance?: EnergyPerformanceEvidence;
}

export interface SegmentEnergyResult {
  segmentId: string;
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
  initialStateOfHealthPercent: number;
  referenceWindKt: number;
  referenceTemperatureC: number;
}

export interface ReadOnlyTelemetry {
  stateOfChargePercent: number;
  stateOfHealthPercent?: number;
  windKt?: number;
  temperatureC?: number;
  capturedAtUtc?: string;
}

const SEGMENT_KINDS = new Set<EnergySegment["kind"]>([
  "climb", "cruise", "work", "hold", "return", "diversion", "contingency",
]);
const DEFAULT_BASE_POWER_W: Record<EnergySegment["kind"], number> = {
  climb: 100,
  cruise: 80,
  work: 100,
  hold: 70,
  return: 85,
  diversion: 90,
  contingency: 75,
};
const KIND_FACTOR: Record<EnergySegment["kind"], number> = {
  climb: 1.25,
  cruise: 1,
  work: 1.1,
  hold: 0.9,
  return: 1.05,
  diversion: 1.1,
  contingency: 1,
};
const DEFAULT_ENERGY_PER_NM_WH = 0.75;
const DEFAULT_PAYLOAD_POWER_PER_KG_W = 2;
const DEFAULT_UNCERTAINTY_PERCENT = 5;
const UTC_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/;

function parseUtc(value: unknown): number | undefined {
  if (typeof value !== "string") return undefined;
  const match = UTC_PATTERN.exec(value);
  if (!match) return undefined;
  const [, year, month, day, hour, minute, second, fraction = ""] = match;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return undefined;
  if (date.getUTCFullYear() !== Number(year)
    || date.getUTCMonth() + 1 !== Number(month)
    || date.getUTCDate() !== Number(day)
    || date.getUTCHours() !== Number(hour)
    || date.getUTCMinutes() !== Number(minute)
    || date.getUTCSeconds() !== Number(second)
    || date.getUTCMilliseconds() !== Number(fraction.padEnd(3, "0") || 0)) return undefined;
  return date.getTime();
}

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function finiteNonnegative(value: unknown): value is number {
  return finite(value) && value >= 0;
}

function percentage(value: unknown): value is number {
  return finite(value) && value >= 0 && value <= 100;
}

function nonempty(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function validRefs(value: unknown): value is readonly string[] {
  return Array.isArray(value) && value.length > 0 && value.every(nonempty);
}

function uniqueRefs(...sources: readonly (readonly string[] | undefined)[]): string[] {
  const refs: string[] = [];
  for (const source of sources) {
    for (const ref of source ?? []) if (nonempty(ref) && !refs.includes(ref)) refs.push(ref);
  }
  return refs;
}

function approximateEqual(actual: number, expected: number): boolean {
  return Math.abs(actual - expected) <= 1e-6 * Math.max(1, Math.abs(actual), Math.abs(expected));
}

function canonical(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "number") {
    if (Number.isNaN(value)) return '"NaN"';
    if (value === Infinity) return '"Infinity"';
    if (value === -Infinity) return '"-Infinity"';
    return JSON.stringify(value);
  }
  if (typeof value === "string" || typeof value === "boolean") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record).filter((key) => record[key] !== undefined).sort().map((key) => `${JSON.stringify(key)}:${canonical(record[key])}`).join(",")}}`;
  }
  return JSON.stringify(String(value));
}

function snapshotHash(input: EnergyModelInput): string {
  return createHash("sha256").update(canonical(input)).digest("hex");
}

function modelRefs(input: EnergyModelInput): string[] {
  const versionFallback = input.performanceEvidenceRefs === undefined && nonempty(input.modelVersion)
    ? [input.modelVersion]
    : input.performanceEvidenceRefs;
  return uniqueRefs(versionFallback, input.performance?.evidenceRefs);
}

function resultBase(input: EnergyModelInput, status: EnergyModelResult["status"], limitingAssumption: string, evidenceRefs: readonly string[]): EnergyModelResult {
  return {
    aircraftId: typeof input.aircraftId === "string" ? input.aircraftId : "",
    modelVersion: typeof input.modelVersion === "string" ? input.modelVersion : "",
    inputSnapshotHash: snapshotHash(input),
    segmentResults: [],
    predictedAtRecoveryPercent: 0,
    diversionReservePercent: 0,
    contingencyReservePercent: 0,
    uncertaintyPercent: 0,
    limitingAssumption,
    status,
    approvedReserve: { ...input.approvedReserve },
    evidenceRefs: [...evidenceRefs],
    initialStateOfChargePercent: finite(input.battery?.stateOfChargePercent) ? input.battery.stateOfChargePercent : 0,
    initialStateOfHealthPercent: finite(input.battery?.stateOfHealthPercent) ? input.battery.stateOfHealthPercent : 0,
    referenceWindKt: finite(input.weather?.windKt) ? input.weather.windKt : 0,
    referenceTemperatureC: finite(input.weather?.temperatureC) ? input.weather.temperatureC : 20,
  };
}

function invalidSegment(segment: EnergySegment): string | undefined {
  if (!nonempty(segment.id) || !SEGMENT_KINDS.has(segment.kind)) return "SEGMENT_ID_OR_KIND_UNKNOWN";
  if (!finiteNonnegative(segment.distanceNm) || !finiteNonnegative(segment.distanceM) || !approximateEqual(segment.distanceM, segment.distanceNm * 1852)) {
    return "SEGMENT_DISTANCE_NORMALIZATION_UNKNOWN";
  }
  if (!finiteNonnegative(segment.durationS)) return "SEGMENT_DURATION_UNKNOWN";
  if (segment.durationMinutes !== undefined && (!finiteNonnegative(segment.durationMinutes) || !approximateEqual(segment.durationS, segment.durationMinutes * 60))) {
    return "SEGMENT_DURATION_NORMALIZATION_UNKNOWN";
  }
  if (segment.altitudeChangeFt !== undefined && (!finite(segment.altitudeChangeFt) || segment.altitudeChangeM === undefined || !finite(segment.altitudeChangeM) || !approximateEqual(segment.altitudeChangeM, segment.altitudeChangeFt * 0.3048))) {
    return "SEGMENT_ALTITUDE_NORMALIZATION_UNKNOWN";
  }
  if (segment.altitudeChangeM !== undefined && segment.altitudeChangeFt === undefined) return "SEGMENT_ALTITUDE_NORMALIZATION_UNKNOWN";
  if (segment.expectedGroundspeedKt !== undefined && (!finite(segment.expectedGroundspeedKt) || segment.expectedGroundspeedKt <= 0 || segment.expectedGroundspeedMps === undefined || !finite(segment.expectedGroundspeedMps) || !approximateEqual(segment.expectedGroundspeedMps, segment.expectedGroundspeedKt * 0.5144444444444445))) {
    return "SEGMENT_GROUNDSPEED_NORMALIZATION_UNKNOWN";
  }
  if (segment.expectedGroundspeedMps !== undefined && segment.expectedGroundspeedKt === undefined) return "SEGMENT_GROUNDSPEED_NORMALIZATION_UNKNOWN";
  if (segment.payloadPowerW !== undefined && !finiteNonnegative(segment.payloadPowerW)) return "SEGMENT_PAYLOAD_POWER_UNKNOWN";
  if (segment.distanceNm > 0 && segment.durationS === 0 && segment.expectedGroundspeedKt === undefined) return "SEGMENT_TIME_OR_SPEED_UNKNOWN";
  return undefined;
}

function validReservePolicy(policy: ReservePolicy): boolean {
  return percentage(policy.recoveryMinimumPercent)
    && percentage(policy.diversionMinimumPercent)
    && percentage(policy.contingencyMinimumPercent)
    && policy.uncertaintyMethod === "approved-model"
    && parseUtc(policy.effectiveFromUtc) !== undefined;
}

function validBattery(input: EnergyModelInput): string | undefined {
  const battery = input.battery;
  if (!battery || !nonempty(input.aircraftId) || !Array.isArray(battery.aircraftCompatibility)) return "BATTERY_DATA_UNKNOWN";
  if (!battery.aircraftCompatibility.includes(input.aircraftId)) return "BATTERY_AIRCRAFT_INCOMPATIBLE";
  if (battery.status !== "released") return "BATTERY_NOT_RELEASED";
  if (!finite(battery.nominalCapacityWh) || battery.nominalCapacityWh <= 0 || !finite(battery.nominalEnergyJ) || !approximateEqual(battery.nominalEnergyJ, battery.nominalCapacityWh * 3600)) return "BATTERY_CAPACITY_UNKNOWN";
  if (!percentage(battery.stateOfChargePercent) || !percentage(battery.stateOfHealthPercent)) return "BATTERY_HEALTH_UNKNOWN";
  if (battery.stateOfHealthPercent <= 0) return "BATTERY_HEALTH_UNUSABLE";
  if (!finiteNonnegative(battery.cycles) || !finiteNonnegative(battery.ageDays)) return "BATTERY_HISTORY_UNKNOWN";
  return undefined;
}

function performanceValues(input: EnergyModelInput): { basePowerWByKind: Record<EnergySegment["kind"], number>; energyPerNmWh: number; payloadPowerPerKgW: number; uncertaintyPercent: number } | undefined {
  const performance = input.performance;
  const basePowerWByKind = { ...DEFAULT_BASE_POWER_W, ...(performance?.basePowerWByKind ?? {}) };
  if (Object.values(basePowerWByKind).some((value) => !finiteNonnegative(value) || value <= 0)) return undefined;
  const energyPerNmWh = performance?.energyPerNmWh ?? DEFAULT_ENERGY_PER_NM_WH;
  const payloadPowerPerKgW = performance?.payloadPowerPerKgW ?? DEFAULT_PAYLOAD_POWER_PER_KG_W;
  const uncertaintyPercent = performance?.uncertaintyPercent ?? DEFAULT_UNCERTAINTY_PERCENT;
  if (!finiteNonnegative(energyPerNmWh) || !finiteNonnegative(payloadPowerPerKgW) || !finiteNonnegative(uncertaintyPercent)) return undefined;
  return { basePowerWByKind, energyPerNmWh, payloadPowerPerKgW, uncertaintyPercent };
}

function reserveStatus(
  result: Pick<EnergyModelResult, "predictedAtRecoveryPercent" | "diversionReservePercent" | "contingencyReservePercent" | "uncertaintyPercent" | "approvedReserve">,
): { status: "pass" | "blocked"; reason: string } {
  const checks: readonly [number, number, string][] = [
    [result.predictedAtRecoveryPercent, result.approvedReserve.recoveryMinimumPercent, "RECOVERY_RESERVE_BELOW_APPROVED_MINIMUM"],
    [result.diversionReservePercent, result.approvedReserve.diversionMinimumPercent, "DIVERSION_RESERVE_BELOW_APPROVED_MINIMUM"],
    [result.contingencyReservePercent, result.approvedReserve.contingencyMinimumPercent, "CONTINGENCY_RESERVE_BELOW_APPROVED_MINIMUM"],
  ];
  const failed = checks.find(([available, minimum]) => available - result.uncertaintyPercent < minimum);
  return failed === undefined ? { status: "pass", reason: "APPROVED_RESERVE_REQUIREMENTS_MET" } : { status: "blocked", reason: failed[2] };
}

export function calculateMissionEnergy(input: EnergyModelInput): EnergyModelResult {
  const evidenceRefs = modelRefs(input);
  if (!nonempty(input.aircraftId) || !nonempty(input.modelVersion)) return resultBase(input, "unknown", "MODEL_ID_UNKNOWN", evidenceRefs);
  if (!validRefs(evidenceRefs)) return resultBase(input, "unknown", "PERFORMANCE_EVIDENCE_REQUIRED", evidenceRefs);
  if (!validReservePolicy(input.approvedReserve)) return resultBase(input, "unknown", "RESERVE_POLICY_UNKNOWN", evidenceRefs);
  if (!finiteNonnegative(input.payloadMassKg)) return resultBase(input, "unknown", "PAYLOAD_MASS_UNKNOWN", evidenceRefs);
  if (!finite(input.weather.windKt) || !finite(input.weather.temperatureC) || (input.weather.densityAltitudeFt !== undefined && !finite(input.weather.densityAltitudeFt))) {
    return resultBase(input, "unknown", "WEATHER_INPUT_UNKNOWN", evidenceRefs);
  }
  const batteryReason = validBattery(input);
  if (batteryReason !== undefined) {
    return resultBase(input, batteryReason === "BATTERY_NOT_RELEASED" || batteryReason === "BATTERY_AIRCRAFT_INCOMPATIBLE" || batteryReason === "BATTERY_HEALTH_UNUSABLE" ? "blocked" : "unknown", batteryReason, evidenceRefs);
  }
  if (!Array.isArray(input.segments) || input.segments.length === 0) return resultBase(input, "unknown", "SEGMENTS_REQUIRED", evidenceRefs);
  const performance = performanceValues(input);
  if (performance === undefined) return resultBase(input, "unknown", "PERFORMANCE_MODEL_UNKNOWN", evidenceRefs);
  for (const segment of input.segments) {
    const reason = invalidSegment(segment);
    if (reason !== undefined) return resultBase(input, "unknown", reason, evidenceRefs);
  }

  const usableWh = input.battery.nominalCapacityWh * (input.battery.stateOfHealthPercent / 100);
  const startingWh = usableWh * (input.battery.stateOfChargePercent / 100);
  const adverseWindKt = Math.max(0, input.weather.windKt);
  const densityFactor = 1 + Math.max(0, input.weather.densityAltitudeFt ?? 0) / 10_000 * 0.1;
  const temperatureFactor = 1 + Math.abs(input.weather.temperatureC - 20) * 0.005;
  const results: SegmentEnergyResult[] = [];
  let consumedWh = 0;
  let lastReturn: number | undefined;
  let lastDiversion: number | undefined;
  let lastContingency: number | undefined;
  let totalUncertainty = performance.uncertaintyPercent + Math.abs(input.weather.windKt) * 0.05 + Math.abs(input.weather.temperatureC - 20) * 0.05;

  input.segments.forEach((segment, index) => {
    const kind = segment.kind as EnergySegment["kind"];
    const durationHours = segment.durationS > 0
      ? segment.durationS / 3600
      : segment.distanceNm / (segment.expectedGroundspeedKt ?? 1);
    const speedKt = segment.expectedGroundspeedKt ?? (durationHours > 0 ? segment.distanceNm / durationHours : 1);
    const payloadPowerW = segment.payloadPowerW ?? input.payloadMassKg * performance.payloadPowerPerKgW;
    const altitudeClimbM = Math.max(0, segment.altitudeChangeM ?? 0);
    const climbEnergyWh = altitudeClimbM * 0.002;
    const baseEnergyWh = (performance.basePowerWByKind[kind] + payloadPowerW) * durationHours
      + segment.distanceNm * performance.energyPerNmWh
      + climbEnergyWh;
    const windFactor = 1 + adverseWindKt / Math.max(1, speedKt) * 0.25;
    const altitudeFactor = 1 + altitudeClimbM / 2_000 * 0.05;
    const energyWh = baseEnergyWh * KIND_FACTOR[kind] * windFactor * temperatureFactor * densityFactor * altitudeFactor;
    const demandPercent = energyWh / usableWh * 100;
    consumedWh += energyWh;
    const remainingPercent = Math.max(0, (startingWh - consumedWh) / usableWh * 100);
    const segmentUncertainty = totalUncertainty;
    results.push({ segmentId: segment.id, demandPercent, remainingPercent, uncertaintyPercent: segmentUncertainty });
    if (segment.kind === "return") lastReturn = index;
    if (segment.kind === "diversion") lastDiversion = index;
    if (segment.kind === "contingency") lastContingency = index;
  });

  totalUncertainty = Math.max(totalUncertainty, results.reduce((maximum, result) => Math.max(maximum, result.uncertaintyPercent), 0));
  const finalResult = results.at(-1)!;
  const predictedAtRecoveryPercent = results[lastReturn ?? results.length - 1].remainingPercent;
  const diversionReservePercent = results[lastDiversion ?? lastReturn ?? results.length - 1].remainingPercent;
  const contingencyReservePercent = results[lastContingency ?? lastDiversion ?? lastReturn ?? results.length - 1].remainingPercent;
  const base = {
    aircraftId: input.aircraftId,
    modelVersion: input.modelVersion,
    inputSnapshotHash: snapshotHash(input),
    segmentResults: results,
    predictedAtRecoveryPercent,
    diversionReservePercent,
    contingencyReservePercent,
    uncertaintyPercent: totalUncertainty,
    limitingAssumption: "APPROVED_PERFORMANCE_MODEL",
    status: "pass" as const,
    approvedReserve: { ...input.approvedReserve },
    evidenceRefs,
    initialStateOfChargePercent: input.battery.stateOfChargePercent,
    initialStateOfHealthPercent: input.battery.stateOfHealthPercent,
    referenceWindKt: input.weather.windKt,
    referenceTemperatureC: input.weather.temperatureC,
  };
  const reserve = reserveStatus(base);
  return {
    ...base,
    limitingAssumption: reserve.reason === "APPROVED_RESERVE_REQUIREMENTS_MET" ? "APPROVED_PERFORMANCE_MODEL" : reserve.reason,
    status: reserve.status,
    segmentResults: results.map((result, index) => index === results.length - 1 && finalResult.remainingPercent === 0
      ? { ...result, limitingAssumption: "BATTERY_ENERGY_DEPLETED_BEFORE_COMPLETION" }
      : result),
  };
}

export function updateReadOnlyEstimate(previous: EnergyModelResult, telemetry: ReadOnlyTelemetry): EnergyModelResult {
  const evidenceRefs = [...previous.evidenceRefs];
  if (!percentage(telemetry.stateOfChargePercent)
    || (telemetry.stateOfHealthPercent !== undefined && !percentage(telemetry.stateOfHealthPercent))
    || (telemetry.windKt !== undefined && !finite(telemetry.windKt))
    || (telemetry.temperatureC !== undefined && !finite(telemetry.temperatureC))
    || (telemetry.capturedAtUtc !== undefined && parseUtc(telemetry.capturedAtUtc) === undefined)) {
    return { ...previous, status: "unknown", limitingAssumption: "READ_ONLY_TELEMETRY_UNKNOWN", evidenceRefs };
  }
  const stateOfChargeDelta = telemetry.stateOfChargePercent - previous.initialStateOfChargePercent;
  const healthPenalty = Math.max(0, previous.initialStateOfHealthPercent - (telemetry.stateOfHealthPercent ?? previous.initialStateOfHealthPercent)) * 0.2;
  const windPenalty = Math.max(0, (telemetry.windKt ?? previous.referenceWindKt) - previous.referenceWindKt) * 0.1;
  const temperaturePenalty = Math.abs((telemetry.temperatureC ?? previous.referenceTemperatureC) - previous.referenceTemperatureC) * 0.02;
  const adjustment = stateOfChargeDelta - healthPenalty - windPenalty - temperaturePenalty;
  const conservativeUpdate = (value: number): number => Math.max(0, Math.min(value, value + adjustment));
  const estimate = {
    ...previous,
    predictedAtRecoveryPercent: conservativeUpdate(previous.predictedAtRecoveryPercent),
    diversionReservePercent: conservativeUpdate(previous.diversionReservePercent),
    contingencyReservePercent: conservativeUpdate(previous.contingencyReservePercent),
    uncertaintyPercent: Math.max(previous.uncertaintyPercent, previous.uncertaintyPercent + healthPenalty + windPenalty + temperaturePenalty),
    limitingAssumption: "READ_ONLY_TELEMETRY_ESTIMATE",
  };
  const reserve = reserveStatus(estimate);
  return {
    ...estimate,
    status: reserve.status,
    limitingAssumption: reserve.status === "pass" ? estimate.limitingAssumption : reserve.reason,
  };
}

export function assertReserveNeverDecreases(approved: EnergyModelResult, estimate: EnergyModelResult): void {
  const approvedMinimums = approved.approvedReserve;
  const estimateMinimums = estimate.approvedReserve;
  if (estimateMinimums.recoveryMinimumPercent < approvedMinimums.recoveryMinimumPercent
    || estimateMinimums.diversionMinimumPercent < approvedMinimums.diversionMinimumPercent
    || estimateMinimums.contingencyMinimumPercent < approvedMinimums.contingencyMinimumPercent
    || estimate.predictedAtRecoveryPercent < estimateMinimums.recoveryMinimumPercent
    || estimate.diversionReservePercent < estimateMinimums.diversionMinimumPercent
    || estimate.contingencyReservePercent < estimateMinimums.contingencyMinimumPercent) {
    throw new Error("approved reserve minimum cannot be lowered by read-only telemetry");
  }
}
