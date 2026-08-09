import { parseFlightPlanDraft } from "./types.js";
import type { FlightPlanDraft, GeoFinding, GeoSafetyResult, RoutePlan } from "./types.js";

export type FlightPlanAircraftClass = "IA" | "IB" | "IC" | "II" | "III";
export type FlightPlanFlightRule = "VFR" | "IFR";

export interface FlightRuleFacts {
  aircraftClass: FlightPlanAircraftClass;
  flightRule: FlightPlanFlightRule;
  configuration?: "unarmed-isr" | "unarmed-support" | "armed" | "strike";
  ifrApproved?: boolean;
  approvedCapabilityEvidence?: boolean;
  aircraftEquipmentCapable?: boolean;
  segregatedAirspace?: boolean;
  ifrAuthorization?: boolean;
  officialAirspaceCurrent?: boolean;
  sourcePackageIds?: readonly string[];
  calculationVersion?: string;
}

export type FlightPlanExportFormat = "json" | "geojson" | "kml" | "kmz" | "gpx" | "text";

const DEFAULT_CALCULATION_VERSION = "flight-rule-v1";

function unique(values: readonly string[]): string[] { return [...new Set(values.filter((value) => value.trim() !== ""))]; }

function finding(code: string, concept: string, sourcePackageIds: readonly string[]): GeoFinding {
  return { code, severity: "hard", messageConceptId: concept, sourcePackageIds };
}

function result(status: GeoSafetyResult["status"], code: string, concept: string, facts: FlightRuleFacts): GeoSafetyResult {
  const sourcePackageIds = unique(facts.sourcePackageIds ?? []);
  return {
    status,
    findings: status === "pass" ? [] : [finding(code, concept, sourcePackageIds)],
    sourcePackageIds,
    calculationVersion: facts.calculationVersion ?? DEFAULT_CALCULATION_VERSION,
  };
}

/** Apply class, capability, segregated-airspace, and authorization gates without inferring permissions from maps. */
export function evaluateFlightRules(facts: FlightRuleFacts): GeoSafetyResult {
  if (facts.configuration === "armed" || facts.configuration === "strike") return result("blocked", "CONFIGURATION_OUT_OF_SCOPE", "geo.flight.configuration.out_of_scope", facts);
  if (facts.officialAirspaceCurrent === false) return result("unknown", "OFFICIAL_AIRSPACE_UNKNOWN", "geo.flight.airspace.unknown", facts);
  if (facts.flightRule === "VFR") return result("pass", "", "", facts);
  if (facts.aircraftClass === "IA" || facts.aircraftClass === "IB") return result("blocked", "IFR_CLASS_NOT_ELIGIBLE", "geo.flight.ifr.class_not_eligible", facts);
  const required: Array<[keyof Pick<FlightRuleFacts, "ifrApproved" | "approvedCapabilityEvidence" | "aircraftEquipmentCapable" | "segregatedAirspace" | "ifrAuthorization">, string, string]> = [
    ["ifrApproved", "IFR_APPROVAL_UNKNOWN", "geo.flight.ifr.approval.unknown"],
    ["approvedCapabilityEvidence", "IFR_CAPABILITY_UNKNOWN", "geo.flight.ifr.capability.unknown"],
    ["aircraftEquipmentCapable", "IFR_EQUIPMENT_UNKNOWN", "geo.flight.ifr.equipment.unknown"],
    ["segregatedAirspace", "IFR_AIRSPACE_UNKNOWN", "geo.flight.ifr.airspace.unknown"],
    ["ifrAuthorization", "IFR_AUTHORIZATION_UNKNOWN", "geo.flight.ifr.authorization.unknown"],
  ];
  for (const [field, unknownCode, concept] of required) {
    if (facts[field] === false) return result("blocked", unknownCode.replace("_UNKNOWN", "_MISSING"), concept.replace("unknown", "missing"), facts);
    if (facts[field] !== true) return result("unknown", unknownCode, concept, facts);
  }
  return result("pass", "", "", facts);
}

function routeCoordinates(route: RoutePlan): string {
  return route.waypoints.map((waypoint) => `${waypoint.lon},${waypoint.lat},${waypoint.altitude}`).join(" ");
}

function geoJson(draft: FlightPlanDraft): string {
  const route = draft.route;
  return JSON.stringify({
    type: "FeatureCollection",
    properties: { missionId: draft.missionId, formatVersion: draft.formatVersion, altitudeReference: route.altitudeReference, transmission: draft.transmission },
    features: [{
      type: "Feature",
      properties: { routeId: route.id, altitudeReference: route.altitudeReference, sourcePackageIds: route.sourcePackageIds, checks: draft.checks },
      geometry: { type: "LineString", coordinates: route.waypoints.map((waypoint) => [waypoint.lon, waypoint.lat, waypoint.altitude]) },
    }],
  });
}

function kml(draft: FlightPlanDraft): string {
  const coordinates = routeCoordinates(draft.route);
  return `<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>${draft.missionId}</name><Placemark><name>${draft.route.id}</name><ExtendedData><Data name="transmission"><value>not-supported</value></Data><Data name="altitudeReference"><value>${draft.route.altitudeReference}</value></Data></ExtendedData><LineString><altitudeMode>absolute</altitudeMode><coordinates>${coordinates}</coordinates></LineString></Placemark></Document></kml>`;
}

function gpx(draft: FlightPlanDraft): string {
  const points = draft.route.waypoints.map((waypoint) => `<rtept lat="${waypoint.lat}" lon="${waypoint.lon}"><ele>${waypoint.altitude}</ele><name>${waypoint.id}</name></rtept>`).join("");
  return `<?xml version="1.0" encoding="UTF-8"?><gpx version="1.1" creator="FAC-ISR-SMS" xmlns="http://www.topografix.com/GPX/1/1"><metadata><name>${draft.missionId}</name></metadata><rte><name>${draft.route.id}</name>${points}</rte></gpx>`;
}

function textDraft(draft: FlightPlanDraft): string {
  const checkStatus = draft.checks.length === 0 ? "none" : draft.checks.map((check) => check.status).join(",");
  return [
    `Mission / Misión: ${draft.missionId}`,
    `Route / Ruta: ${draft.route.id}`,
    `Altitude reference / Referencia vertical: ${draft.route.altitudeReference}`,
    `Checks / Verificaciones: ${checkStatus}`,
    "Draft only / Solo borrador: not-supported",
  ].join("\n");
}

function crc32(data: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of data) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function u16(value: number): number[] { return [value & 0xff, (value >>> 8) & 0xff]; }
function u32(value: number): number[] { return [value & 0xff, (value >>> 8) & 0xff, (value >>> 16) & 0xff, (value >>> 24) & 0xff]; }

/** Produce a minimal standards-compatible stored ZIP containing doc.kml for KMZ export. */
function kmz(kmlText: string): Uint8Array {
  const encoder = new TextEncoder();
  const filename = encoder.encode("doc.kml");
  const data = encoder.encode(kmlText);
  const checksum = crc32(data);
  const local = new Uint8Array([
    ...u32(0x04034b50), ...u16(20), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(checksum), ...u32(data.length), ...u32(data.length), ...u16(filename.length), ...u16(0), ...filename, ...data,
  ]);
  const central = new Uint8Array([
    ...u32(0x02014b50), ...u16(20), ...u16(20), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(checksum), ...u32(data.length), ...u32(data.length), ...u16(filename.length), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(0), ...u32(0), ...filename,
  ]);
  const end = new Uint8Array([...u32(0x06054b50), ...u16(0), ...u16(0), ...u16(1), ...u16(1), ...u32(central.length), ...u32(local.length), ...u16(0)]);
  const output = new Uint8Array(local.length + central.length + end.length);
  output.set(local, 0); output.set(central, local.length); output.set(end, local.length + central.length);
  return output;
}

export function exportDraft(draft: FlightPlanDraft, format: Exclude<FlightPlanExportFormat, "kmz">): string;
export function exportDraft(draft: FlightPlanDraft, format: "kmz"): Uint8Array;
export function exportDraft(draft: FlightPlanDraft, format: FlightPlanExportFormat): Uint8Array | string {
  const parsed = parseFlightPlanDraft(draft);
  if (format === "json") return JSON.stringify(parsed, null, 2);
  if (format === "geojson") return geoJson(parsed);
  if (format === "kml") return kml(parsed);
  if (format === "gpx") return gpx(parsed);
  if (format === "kmz") return kmz(kml(parsed));
  if (format === "text") return textDraft(parsed);
  throw new RangeError(`unsupported flight-plan export format: ${format}`);
}

export { createFlightPlanDraft } from "./types.js";
