import { createHash } from "node:crypto";
import type { GeoFinding, RoutePlan } from "./types.js";

export type WeatherSource = "metar" | "taf" | "sigmet" | "winds-aloft" | "local-observation";
export type WeatherAuthorityClass = "official" | "approved-local-observer";

export interface CloudLayer {
  amount: string;
  baseFtAgl?: number;
  type?: "CB" | "TCU";
}

export interface WeatherObservation {
  id: string;
  station: string;
  observedAtUtc: string;
  source: WeatherSource;
  issuedAtUtc?: string;
  validFromUtc?: string;
  validUntilUtc?: string;
  visibilityM?: number;
  cloudLayers?: readonly CloudLayer[];
  windKt?: { directionDeg?: number; speedKt: number; gustKt?: number };
  temperatureC?: number;
  qnhHpa?: number;
  phenomenon?: string;
  raw: string;
  sourcePackageId: string;
  authorityClass: WeatherAuthorityClass;
  parseWarnings?: readonly string[];
}

export interface WeatherRouteInput {
  route?: RoutePlan;
  observations: readonly WeatherObservation[];
  nowUtc: string;
  maxAgeMinutes?: number;
  minimumVisibilityM?: number;
  minimumCeilingFtAgl?: number;
  maxWindKt?: number;
  maxGustKt?: number;
  calculationVersion?: string;
}

export interface WeatherSafetyResult {
  status: "pass" | "blocked" | "unknown" | "expired";
  observations: readonly WeatherObservation[];
  findings: readonly GeoFinding[];
  maxAgeMinutes: number;
  calculationVersion: string;
}

const DEFAULT_MAX_AGE_MINUTES = 60;
const DEFAULT_CALCULATION_VERSION = "weather-gate-v1";
const FALLBACK_UTC = "1970-01-01T00:00:00Z";
const UTC = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/;
const FULL_UTC = /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z/;

function finite(value: unknown): value is number { return typeof value === "number" && Number.isFinite(value); }

function isExactUtc(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = UTC.exec(value);
  if (!match) return false;
  const [, year, month, day, hour, minute, second, fraction = ""] = match;
  const date = new Date(value);
  return Number.isFinite(date.getTime())
    && date.getUTCFullYear() === Number(year)
    && date.getUTCMonth() + 1 === Number(month)
    && date.getUTCDate() === Number(day)
    && date.getUTCHours() === Number(hour)
    && date.getUTCMinutes() === Number(minute)
    && date.getUTCSeconds() === Number(second)
    && date.getUTCMilliseconds() === Number(fraction.padEnd(3, "0") || 0);
}

function unique(values: readonly string[]): string[] { return [...new Set(values.filter((value) => value.trim() !== ""))]; }

function idFor(source: WeatherSource, raw: string, sourcePackageId: string): string {
  return `${source}-${createHash("sha256").update(`${sourcePackageId}\n${raw}`).digest("hex").slice(0, 16)}`;
}

function fullTimestamp(raw: string): string | undefined {
  const match = raw.match(FULL_UTC);
  return match?.[0];
}

function signedNumber(value: string): number {
  return value.startsWith("M") ? -Number(value.slice(1)) : Number(value);
}

function inferDayTime(raw: string, referenceUtc?: string): string | undefined {
  const match = raw.match(/\b(\d{2})(\d{2})(\d{2})Z\b/);
  if (!match || !isExactUtc(referenceUtc)) return undefined;
  const [, day, hour, minute] = match;
  const reference = new Date(referenceUtc);
  const inferred = new Date(Date.UTC(reference.getUTCFullYear(), reference.getUTCMonth(), Number(day), Number(hour), Number(minute)));
  if (inferred.getTime() > reference.getTime() + 36 * 60 * 60 * 1000) inferred.setUTCMonth(inferred.getUTCMonth() - 1);
  return inferred.toISOString().replace(".000Z", "Z");
}

function issueTime(raw: string, referenceUtc: string | undefined, warnings: string[]): string {
  const full = fullTimestamp(raw) ?? inferDayTime(raw, referenceUtc);
  if (full !== undefined) return full;
  warnings.push("issue time requires a full UTC reference date");
  return FALLBACK_UTC;
}

function station(raw: string): string {
  return raw.match(/\b[A-Z]{4}\b/)?.[0] ?? "UNKNOWN";
}

function parseWind(raw: string): WeatherObservation["windKt"] {
  const match = raw.match(/\b(VRB|\d{3})(\d{2})(?:G(\d{2}))?(KT|MPS)\b/);
  if (!match) return undefined;
  const [, direction, speed, gust, unit] = match;
  const conversion = unit === "MPS" ? 1.943844492 : 1;
  return {
    ...(direction === "VRB" ? {} : { directionDeg: Number(direction) }),
    speedKt: Number(speed) * conversion,
    ...(gust === undefined ? {} : { gustKt: Number(gust) * conversion }),
  };
}

function parseVisibility(raw: string): number | undefined {
  const weatherText = raw.replace(FULL_UTC, " ");
  const compactStatute = weatherText.match(/\bP?(\d+(?:\.\d+)?)SM\b/);
  if (compactStatute !== null) return Number(compactStatute[1]) * 1_609.344;
  const statute = weatherText.match(/\b(?:(\d+)\s+)?(?:(\d)\/(\d))?SM\b/);
  if (statute) {
    const whole = Number(statute[1] ?? 0);
    const fraction = statute[2] === undefined ? 0 : Number(statute[2]) / Number(statute[3]);
    return (whole + fraction) * 1_609.344;
  }
  for (const metric of weatherText.matchAll(/\b(P?\d{4})\b/g)) {
    const index = metric.index ?? -1;
    const before = index > 0 ? weatherText[index - 1] : "";
    const after = weatherText[index + metric[0].length] ?? "";
    if (before === "/" || after === "/") continue;
    if (metric[1] !== "////") return Number(metric[1].replace(/^P/, ""));
  }
  return undefined;
}

function parseClouds(raw: string): CloudLayer[] {
  const layers: CloudLayer[] = [];
  const pattern = /\b(FEW|SCT|BKN|OVC)(\d{3})(CB|TCU)?\b/g;
  for (const match of raw.matchAll(pattern)) {
    layers.push({ amount: match[1], baseFtAgl: Number(match[2]) * 100, ...(match[3] === undefined ? {} : { type: match[3] as "CB" | "TCU" }) });
  }
  return layers;
}

function parseTemperature(raw: string): number | undefined {
  const match = raw.match(/\b(M?\d{2})\/(?:M?\d{2})\b/);
  return match === null ? undefined : signedNumber(match[1]);
}

function parseQnh(raw: string): number | undefined {
  const qnh = raw.match(/\bQ(\d{4})\b/);
  if (qnh !== null) return Number(qnh[1]);
  const altimeter = raw.match(/\bA(\d{4})\b/);
  return altimeter === null ? undefined : Number(altimeter[1]) * 33.8638866667;
}

function parseValidity(raw: string, referenceUtc: string): { validFromUtc?: string; validUntilUtc?: string } {
  const tafMatch = raw.match(/\b(\d{2})(\d{2})\/(\d{2})(\d{2})\b/);
  const sigmetMatch = raw.match(/\b(\d{2})(\d{4})\/(\d{2})(\d{4})\b/);
  const match = tafMatch === null ? sigmetMatch : tafMatch;
  if (match === null || !isExactUtc(referenceUtc)) return {};
  const [, fromDay, fromHourOrTime, toDay, toHourOrTime] = match;
  const fromTime = fromHourOrTime.length === 2 ? `${fromHourOrTime}00` : fromHourOrTime;
  const toTime = toHourOrTime.length === 2 ? `${toHourOrTime}00` : toHourOrTime;
  const reference = new Date(referenceUtc);
  const from = new Date(Date.UTC(reference.getUTCFullYear(), reference.getUTCMonth(), Number(fromDay), Number(fromTime.slice(0, 2)), Number(fromTime.slice(2))));
  const to = new Date(Date.UTC(reference.getUTCFullYear(), reference.getUTCMonth(), Number(toDay), Number(toTime.slice(0, 2)), Number(toTime.slice(2))));
  if (from.getTime() > reference.getTime() + 36 * 60 * 60 * 1000) from.setUTCMonth(from.getUTCMonth() - 1);
  while (to.getTime() <= from.getTime()) to.setUTCMonth(to.getUTCMonth() + 1);
  return { validFromUtc: from.toISOString().replace(".000Z", "Z"), validUntilUtc: to.toISOString().replace(".000Z", "Z") };
}

function baseObservation(raw: string, sourcePackageId: string, source: WeatherSource, referenceUtc: string | undefined, requireWindAndVisibility: boolean): WeatherObservation {
  const original = typeof raw === "string" ? raw : "";
  const text = original.trim();
  const warnings: string[] = [];
  if (text === "") warnings.push("weather raw text is empty");
  if (sourcePackageId.trim() === "") warnings.push("source package ID is missing");
  const observedAtUtc = issueTime(text, referenceUtc, warnings);
  const parsedWind = parseWind(text);
  const parsedVisibility = parseVisibility(text);
  if (requireWindAndVisibility && parsedWind === undefined) warnings.push("wind group is missing or malformed");
  if (requireWindAndVisibility && parsedVisibility === undefined) warnings.push("visibility group is missing or malformed");
  const observation: WeatherObservation = {
    id: idFor(source, original, sourcePackageId),
    station: station(text),
    observedAtUtc,
    source,
    issuedAtUtc: observedAtUtc,
    visibilityM: parsedVisibility,
    cloudLayers: parseClouds(text),
    windKt: parsedWind,
    temperatureC: parseTemperature(text),
    qnhHpa: parseQnh(text),
    raw: original,
    sourcePackageId,
    authorityClass: "official",
    ...(warnings.length === 0 ? {} : { parseWarnings: warnings }),
  };
  return observation;
}

export function decodeMetar(raw: string, sourcePackageId: string, referenceUtc?: string): WeatherObservation {
  return Object.freeze(baseObservation(raw, sourcePackageId, "metar", referenceUtc, true));
}

export function decodeTaf(raw: string, sourcePackageId: string, referenceUtc?: string): WeatherObservation {
  const observation = baseObservation(raw, sourcePackageId, "taf", referenceUtc, false);
  const validityReference = fullTimestamp(raw) ?? observation.observedAtUtc;
  const validity = parseValidity(raw, validityReference);
  if (validity.validFromUtc === undefined || validity.validUntilUtc === undefined) {
    observation.parseWarnings = [...(observation.parseWarnings ?? []), "TAF validity window is missing or malformed"];
  } else {
    observation.validFromUtc = validity.validFromUtc;
    observation.validUntilUtc = validity.validUntilUtc;
  }
  return Object.freeze(observation);
}

export function decodeSigmet(raw: string, sourcePackageId: string, referenceUtc?: string): WeatherObservation {
  const observation = baseObservation(raw, sourcePackageId, "sigmet", referenceUtc, false);
  const validityReference = fullTimestamp(raw) ?? observation.observedAtUtc;
  const validity = parseValidity(raw, validityReference);
  if (validity.validFromUtc !== undefined) observation.validFromUtc = validity.validFromUtc;
  if (validity.validUntilUtc !== undefined) observation.validUntilUtc = validity.validUntilUtc;
  if (validity.validFromUtc === undefined || validity.validUntilUtc === undefined) {
    observation.parseWarnings = [...(observation.parseWarnings ?? []), "SIGMET validity window is missing or malformed"];
  }
  observation.phenomenon = /\b(TS|TURB|ICE|VA|TC)\b/i.exec(raw)?.[1]?.toUpperCase();
  return Object.freeze(observation);
}

function finding(code: string, concept: string, sourcePackageIds: readonly string[]): GeoFinding {
  return { code, severity: "hard", messageConceptId: concept, sourcePackageIds };
}

function observationState(observation: WeatherObservation, nowUtc: string, maxAgeMinutes: number): "current" | "expired" | "unknown" {
  if (observation.parseWarnings !== undefined && observation.parseWarnings.length > 0) return "unknown";
  if (!isExactUtc(observation.observedAtUtc)) return "unknown";
  const now = Date.parse(nowUtc);
  if (observation.validFromUtc !== undefined && !isExactUtc(observation.validFromUtc)) return "unknown";
  if (observation.validUntilUtc !== undefined && !isExactUtc(observation.validUntilUtc)) return "unknown";
  if (observation.validFromUtc !== undefined && now < Date.parse(observation.validFromUtc)) return "unknown";
  if (observation.validUntilUtc !== undefined && now >= Date.parse(observation.validUntilUtc)) return "expired";
  if (observation.validFromUtc !== undefined && observation.validUntilUtc !== undefined) return "current";
  const ageMinutes = (now - Date.parse(observation.observedAtUtc)) / 60_000;
  if (ageMinutes < 0) return "unknown";
  return ageMinutes > maxAgeMinutes ? "expired" : "current";
}

/** Match source-preserving observations to route limits without treating missing weather as safe. */
export function validateWeatherForRoute(input: WeatherRouteInput): WeatherSafetyResult {
  const maxAgeMinutes = input.maxAgeMinutes ?? DEFAULT_MAX_AGE_MINUTES;
  const calculationVersion = input.calculationVersion ?? DEFAULT_CALCULATION_VERSION;
  const sourcePackageIds = unique([
    ...(input.route?.sourcePackageIds ?? []),
    ...input.observations.map((observation) => observation.sourcePackageId),
  ]);
  const base = { observations: input.observations, maxAgeMinutes, calculationVersion };
  if (!isExactUtc(input.nowUtc) || !finite(maxAgeMinutes) || maxAgeMinutes < 0 || input.observations.length === 0) {
    return { ...base, status: "unknown", findings: [finding("WEATHER_DATA_UNKNOWN", "geo.weather.data.unknown", sourcePackageIds)] };
  }

  const findings: GeoFinding[] = [];
  let hasExpired = false;
  let hasUnknown = false;
  for (const observation of input.observations) {
    const state = observationState(observation, input.nowUtc, maxAgeMinutes);
    if (state === "expired") { hasExpired = true; findings.push(finding("WEATHER_EXPIRED", "geo.weather.expired", [observation.sourcePackageId])); continue; }
    if (state === "unknown") { hasUnknown = true; findings.push(finding("WEATHER_DATA_UNKNOWN", "geo.weather.data.unknown", [observation.sourcePackageId])); continue; }
    if (observation.source === "sigmet") findings.push(finding("SIGMET_HAZARD", "geo.weather.sigmet.hazard", [observation.sourcePackageId]));
    if (input.minimumVisibilityM !== undefined && (observation.visibilityM === undefined || observation.visibilityM < input.minimumVisibilityM)) findings.push(finding("WEATHER_VISIBILITY", "geo.weather.visibility.insufficient", [observation.sourcePackageId]));
    if (input.minimumCeilingFtAgl !== undefined) {
      const ceilings = (observation.cloudLayers ?? []).filter((layer) => (layer.amount === "BKN" || layer.amount === "OVC") && layer.baseFtAgl !== undefined).map((layer) => layer.baseFtAgl!);
      if (ceilings.length === 0 || Math.min(...ceilings) < input.minimumCeilingFtAgl) findings.push(finding("WEATHER_CEILING", "geo.weather.ceiling.insufficient", [observation.sourcePackageId]));
    }
    if (input.maxWindKt !== undefined && (observation.windKt === undefined || observation.windKt.speedKt > input.maxWindKt)) findings.push(finding("WEATHER_WIND", "geo.weather.wind.exceeds_limit", [observation.sourcePackageId]));
    if (input.maxGustKt !== undefined && observation.windKt?.gustKt !== undefined && observation.windKt.gustKt > input.maxGustKt) findings.push(finding("WEATHER_GUST", "geo.weather.gust.exceeds_limit", [observation.sourcePackageId]));
  }
  const status = hasExpired ? "expired" : hasUnknown ? "unknown" : findings.some((item) => item.code !== "") ? "blocked" : "pass";
  return { ...base, status, findings, ...(status === "pass" ? { findings: [] } : {}) };
}
