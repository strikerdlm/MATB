import type {
  CanonicalTelemetry,
  TelemetryValidationOptions,
} from "./types.js";

const UTC_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/;
const TOP_LEVEL_FIELDS = new Set(["eventId", "aircraftId", "observedAtUtc", "position", "motion", "energy", "platform", "route", "sourcePackageIds"]);
const NESTED_FIELDS: Readonly<Record<string, ReadonlySet<string>>> = {
  position: new Set(["lat", "lon", "altitudeMslM", "heightAglM"]),
  motion: new Set(["headingDeg", "groundSpeedKt", "verticalRateFpm"]),
  energy: new Set(["stateOfChargePercent", "voltageV", "currentA", "temperatureC", "reserveAtRecoveryPercent"]),
  platform: new Set(["propulsion", "gnss", "c2Link"]),
  route: new Set(["legId", "crossTrackM", "approvedArea"]),
};

export class TelemetryValidationError extends Error {
  public readonly code = "INVALID_TELEMETRY";

  public constructor(message: string) {
    super(message);
    this.name = "TelemetryValidationError";
  }
}

function objectInput(value: unknown, field: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new TelemetryValidationError(`${field} must be an object`);
  return value as Record<string, unknown>;
}

function text(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "" || value !== value.trim() || value.includes("\0")) throw new TelemetryValidationError(`${field} must be non-empty text`);
  return value;
}

function finiteNumber(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new TelemetryValidationError(`${field} must be finite`);
  return value;
}

function optionalNumber(value: unknown, field: string): number | undefined {
  return value === undefined ? undefined : finiteNumber(value, field);
}

function validateKeys(value: Record<string, unknown>, allowed: ReadonlySet<string>, field: string): void {
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) throw new TelemetryValidationError(`unsupported telemetry field ${field}.${key}`);
  }
}

function utc(value: unknown): string {
  const candidate = text(value, "observedAtUtc");
  if (!UTC_PATTERN.test(candidate)) throw new TelemetryValidationError("observedAtUtc must be UTC ISO-8601");
  const timestamp = new Date(candidate);
  if (!Number.isFinite(timestamp.getTime())) throw new TelemetryValidationError("observedAtUtc must be a valid instant");
  return timestamp.toISOString();
}

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    for (const child of Object.values(value as Record<string, unknown>)) deepFreeze(child);
    Object.freeze(value);
  }
  return value;
}

export function canonicalizeTelemetry(input: unknown, options: TelemetryValidationOptions = {}): CanonicalTelemetry {
  const raw = objectInput(input, "telemetry");
  validateKeys(raw, TOP_LEVEL_FIELDS, "telemetry");
  const eventId = text(raw.eventId, "eventId");
  const aircraftId = text(raw.aircraftId, "aircraftId");
  if (options.aircraftId !== undefined && aircraftId !== options.aircraftId) throw new TelemetryValidationError("aircraftId is not assigned to this gateway");
  const observedAtUtc = utc(raw.observedAtUtc);
  const sourcePackageIds = raw.sourcePackageIds;
  if (!Array.isArray(sourcePackageIds) || sourcePackageIds.length === 0) throw new TelemetryValidationError("sourcePackageIds must contain at least one package");
  const packageIds = sourcePackageIds.map((id) => text(id, "sourcePackageIds"));

  let position: CanonicalTelemetry["position"];
  if (raw.position !== undefined) {
    const value = objectInput(raw.position, "position");
    validateKeys(value, NESTED_FIELDS.position, "position");
    const lat = finiteNumber(value.lat, "position.lat");
    const lon = finiteNumber(value.lon, "position.lon");
    if (lat < -90 || lat > 90) throw new TelemetryValidationError("position.lat must be between -90 and 90");
    if (lon < -180 || lon > 180) throw new TelemetryValidationError("position.lon must be between -180 and 180");
    const altitudeMslM = optionalNumber(value.altitudeMslM, "position.altitudeMslM");
    const heightAglM = optionalNumber(value.heightAglM, "position.heightAglM");
    if (heightAglM !== undefined && heightAglM < 0) throw new TelemetryValidationError("position.heightAglM must be non-negative");
    position = { lat, lon, ...(altitudeMslM === undefined ? {} : { altitudeMslM }), ...(heightAglM === undefined ? {} : { heightAglM }) };
  }

  let motion: CanonicalTelemetry["motion"];
  if (raw.motion !== undefined) {
    const value = objectInput(raw.motion, "motion");
    validateKeys(value, NESTED_FIELDS.motion, "motion");
    const headingDeg = optionalNumber(value.headingDeg, "motion.headingDeg");
    const groundSpeedKt = optionalNumber(value.groundSpeedKt, "motion.groundSpeedKt");
    const verticalRateFpm = optionalNumber(value.verticalRateFpm, "motion.verticalRateFpm");
    if (headingDeg !== undefined && (headingDeg < 0 || headingDeg >= 360)) throw new TelemetryValidationError("motion.headingDeg must be in [0, 360)");
    if (groundSpeedKt !== undefined && groundSpeedKt < 0) throw new TelemetryValidationError("motion.groundSpeedKt must be non-negative");
    motion = { ...(headingDeg === undefined ? {} : { headingDeg }), ...(groundSpeedKt === undefined ? {} : { groundSpeedKt }), ...(verticalRateFpm === undefined ? {} : { verticalRateFpm }) };
  }

  let energy: CanonicalTelemetry["energy"];
  if (raw.energy !== undefined) {
    const value = objectInput(raw.energy, "energy");
    validateKeys(value, NESTED_FIELDS.energy, "energy");
    const stateOfChargePercent = optionalNumber(value.stateOfChargePercent, "energy.stateOfChargePercent");
    const voltageV = optionalNumber(value.voltageV, "energy.voltageV");
    const currentA = optionalNumber(value.currentA, "energy.currentA");
    const temperatureC = optionalNumber(value.temperatureC, "energy.temperatureC");
    const reserveAtRecoveryPercent = optionalNumber(value.reserveAtRecoveryPercent, "energy.reserveAtRecoveryPercent");
    if (stateOfChargePercent !== undefined && (stateOfChargePercent < 0 || stateOfChargePercent > 100)) throw new TelemetryValidationError("energy.stateOfChargePercent must be in [0, 100]");
    if (reserveAtRecoveryPercent !== undefined && (reserveAtRecoveryPercent < 0 || reserveAtRecoveryPercent > 100)) throw new TelemetryValidationError("energy.reserveAtRecoveryPercent must be in [0, 100]");
    energy = { ...(stateOfChargePercent === undefined ? {} : { stateOfChargePercent }), ...(voltageV === undefined ? {} : { voltageV }), ...(currentA === undefined ? {} : { currentA }), ...(temperatureC === undefined ? {} : { temperatureC }), ...(reserveAtRecoveryPercent === undefined ? {} : { reserveAtRecoveryPercent }) };
  }

  let platform: CanonicalTelemetry["platform"];
  if (raw.platform !== undefined) {
    const value = objectInput(raw.platform, "platform");
    validateKeys(value, NESTED_FIELDS.platform, "platform");
    const propulsion = value.propulsion === undefined ? undefined : text(value.propulsion, "platform.propulsion");
    const gnss = value.gnss === undefined ? undefined : text(value.gnss, "platform.gnss");
    const c2Link = value.c2Link === undefined ? undefined : text(value.c2Link, "platform.c2Link");
    if (propulsion !== undefined && !["normal", "degraded", "unknown"].includes(propulsion)) throw new TelemetryValidationError("platform.propulsion is unsupported");
    if (gnss !== undefined && !["normal", "degraded", "unknown"].includes(gnss)) throw new TelemetryValidationError("platform.gnss is unsupported");
    if (c2Link !== undefined && !["normal", "degraded", "lost"].includes(c2Link)) throw new TelemetryValidationError("platform.c2Link is unsupported");
    platform = { ...(propulsion === undefined ? {} : { propulsion: propulsion as "normal" | "degraded" | "unknown" }), ...(gnss === undefined ? {} : { gnss: gnss as "normal" | "degraded" | "unknown" }), ...(c2Link === undefined ? {} : { c2Link: c2Link as "normal" | "degraded" | "lost" }) };
  }

  let route: CanonicalTelemetry["route"];
  if (raw.route !== undefined) {
    const value = objectInput(raw.route, "route");
    validateKeys(value, NESTED_FIELDS.route, "route");
    const legId = value.legId === undefined ? undefined : text(value.legId, "route.legId");
    const crossTrackM = optionalNumber(value.crossTrackM, "route.crossTrackM");
    if (crossTrackM !== undefined && crossTrackM < 0) throw new TelemetryValidationError("route.crossTrackM must be non-negative");
    if (value.approvedArea !== undefined && typeof value.approvedArea !== "boolean") throw new TelemetryValidationError("route.approvedArea must be boolean");
    route = { ...(legId === undefined ? {} : { legId }), ...(crossTrackM === undefined ? {} : { crossTrackM }), ...(value.approvedArea === undefined ? {} : { approvedArea: value.approvedArea }) };
  }

  return deepFreeze({ eventId, aircraftId, observedAtUtc, ...(position === undefined ? {} : { position }), ...(motion === undefined ? {} : { motion }), ...(energy === undefined ? {} : { energy }), ...(platform === undefined ? {} : { platform }), ...(route === undefined ? {} : { route }), sourcePackageIds: packageIds });
}
