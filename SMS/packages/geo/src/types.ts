import type { SignedPackageManifest } from "@fac-isr/evidence";
import { z } from "zod";

export type GeoPackageKind = "map" | "terrain" | "airspace" | "aip" | "notam" | "weather";
export type GeoPackageFormat = "pmtiles" | "mbtiles" | "geotiff" | "cog" | "geojson" | "kml" | "kmz" | "gpx";

export interface LayerManifest {
  id: string;
  title: string;
  authority: string;
  authorityClass: "official" | "open-context" | "local-observation";
  effectiveFromUtc: string;
  expiresAtUtc?: string;
  extent: [number, number, number, number];
  horizontalDatum: string;
  verticalDatum?: string;
  contentSha256: string;
}

export type GeoPackageManifest = Omit<SignedPackageManifest, "kind"> & {
  kind: GeoPackageKind;
  format: GeoPackageFormat;
  horizontalDatum: "EPSG:4326" | string;
  verticalDatum?: string;
  resolution?: string;
  layers: readonly LayerManifest[];
};

export interface Waypoint {
  id: string;
  lat: number;
  lon: number;
  altitude: number;
  altitudeReference: "MSL" | "AGL";
  role: "route" | "hold" | "orbit" | "emergency" | "alternate" | "recovery";
}

export interface RouteSegment {
  id: string;
  fromWaypointId: string;
  toWaypointId: string;
  kind: "track" | "corridor" | "hold" | "orbit" | "area-search";
  geometryHash: string;
}

export interface RoutePlan {
  id: string;
  waypoints: readonly Waypoint[];
  segments: readonly RouteSegment[];
  corridorWidthM?: number;
  flightRule: "VFR" | "IFR";
  visualCondition: "VLOS" | "EVLOS" | "BVLOS";
  altitudeReference: "MSL" | "AGL";
  sourcePackageIds: readonly string[];
}

export interface GeoFinding {
  code: string;
  severity: "hard" | "warning" | "information";
  messageConceptId: string;
  sourcePackageIds: readonly string[];
  location?: { lat: number; lon: number };
}

export interface GeoSafetyResult {
  status: "pass" | "blocked" | "unknown" | "expired";
  findings: readonly GeoFinding[];
  sourcePackageIds: readonly string[];
  calculationVersion: string;
}

export interface FlightPlanDraft {
  formatVersion: string;
  missionId: string;
  route: RoutePlan;
  checks: readonly GeoSafetyResult[];
  transmission: "not-supported";
}

const id = z.string().trim().min(1);
const sha256 = z.string().regex(/^[a-f0-9]{64}$/, "SHA-256 must be lowercase hexadecimal");
const utcPattern = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/;

function isExactUtc(value: string): boolean {
  const match = utcPattern.exec(value);
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

const utc = z.string().regex(utcPattern, "timestamp must be UTC ISO-8601").refine(isExactUtc, "timestamp must be a valid UTC instant");
const latitude = z.number().finite().min(-90).max(90);
const longitude = z.number().finite().min(-180).max(180);
const location = z.object({ lat: latitude, lon: longitude }).strict();
const extent = z.tuple([longitude, latitude, longitude, latitude]).superRefine((value, ctx) => {
  if (value[0] >= value[2]) ctx.addIssue({ code: z.ZodIssueCode.custom, message: "extent west must be less than east" });
  if (value[1] >= value[3]) ctx.addIssue({ code: z.ZodIssueCode.custom, message: "extent south must be less than north" });
});

const LayerSchema = z.object({
  id,
  title: id,
  authority: id,
  authorityClass: z.enum(["official", "open-context", "local-observation"]),
  effectiveFromUtc: utc,
  expiresAtUtc: utc.optional(),
  extent,
  horizontalDatum: id,
  verticalDatum: id.optional(),
  contentSha256: sha256,
}).strict().superRefine((value, ctx) => {
  if (value.expiresAtUtc !== undefined && Date.parse(value.expiresAtUtc) <= Date.parse(value.effectiveFromUtc)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["expiresAtUtc"], message: "layer expiry must follow effective time" });
  }
});

const DependencySchema = z.object({ packageId: id, version: z.string().regex(/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/), contentSha256: sha256 }).strict();
const FileSchema = z.object({ path: id, sha256, sizeBytes: z.number().int().nonnegative() }).strict();
const GeoPackageSchema = z.object({
  schemaVersion: z.literal("1.0"),
  packageId: id,
  kind: z.enum(["map", "terrain", "airspace", "aip", "notam", "weather"]),
  issuer: id,
  version: z.string().regex(/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/),
  issuedAtUtc: utc,
  effectiveFromUtc: utc,
  expiresAtUtc: utc.optional(),
  geographicScope: id,
  contentSha256: sha256,
  signature: z.string().regex(/^[A-Za-z0-9+/]+={0,2}$/, "manifest signature is required"),
  keyId: id,
  dependencies: z.array(DependencySchema),
  files: z.array(FileSchema).min(1),
  qualification: z.enum(["qualified-review", "approved", "blocked"]),
  caveats: z.array(id),
  format: z.enum(["pmtiles", "mbtiles", "geotiff", "cog", "geojson", "kml", "kmz", "gpx"]),
  horizontalDatum: id,
  verticalDatum: id.optional(),
  resolution: id.optional(),
  layers: z.array(LayerSchema).min(1),
}).strict().superRefine((value, ctx) => {
  if (value.expiresAtUtc !== undefined && Date.parse(value.expiresAtUtc) <= Date.parse(value.effectiveFromUtc)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["expiresAtUtc"], message: "package expiry must follow effective time" });
  }
  if (Date.parse(value.issuedAtUtc) > Date.parse(value.effectiveFromUtc)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["issuedAtUtc"], message: "issued time cannot follow effective time" });
  }
  const layerIds = value.layers.map((layer) => layer.id);
  if (new Set(layerIds).size !== layerIds.length) ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["layers"], message: "layer IDs must be unique" });
});

const WaypointSchema = z.object({
  id,
  lat: latitude,
  lon: longitude,
  altitude: z.number().finite(),
  altitudeReference: z.enum(["MSL", "AGL"]),
  role: z.enum(["route", "hold", "orbit", "emergency", "alternate", "recovery"]),
}).strict().superRefine((value, ctx) => {
  if (value.altitudeReference === "AGL" && value.altitude < 0) ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["altitude"], message: "AGL altitude cannot be negative" });
});
const SegmentSchema = z.object({ id, fromWaypointId: id, toWaypointId: id, kind: z.enum(["track", "corridor", "hold", "orbit", "area-search"]), geometryHash: sha256 }).strict();
const RouteSchema = z.object({
  id,
  waypoints: z.array(WaypointSchema).min(2),
  segments: z.array(SegmentSchema).min(1),
  corridorWidthM: z.number().finite().positive().optional(),
  flightRule: z.enum(["VFR", "IFR"]),
  visualCondition: z.enum(["VLOS", "EVLOS", "BVLOS"]),
  altitudeReference: z.enum(["MSL", "AGL"]),
  sourcePackageIds: z.array(id).min(1),
}).strict().superRefine((value, ctx) => {
  const waypointIds = value.waypoints.map((waypoint) => waypoint.id);
  const segmentIds = value.segments.map((segment) => segment.id);
  if (new Set(waypointIds).size !== waypointIds.length) ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["waypoints"], message: "waypoint IDs must be unique" });
  if (new Set(segmentIds).size !== segmentIds.length) ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["segments"], message: "segment IDs must be unique" });
  for (const waypoint of value.waypoints) if (waypoint.altitudeReference !== value.altitudeReference) ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["waypoints"], message: "waypoint altitude reference must match route" });
  for (const segment of value.segments) {
    if (!waypointIds.includes(segment.fromWaypointId) || !waypointIds.includes(segment.toWaypointId)) ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["segments"], message: "segment references an unknown waypoint" });
  }
});

const FindingSchema = z.object({ code: id, severity: z.enum(["hard", "warning", "information"]), messageConceptId: id, sourcePackageIds: z.array(id).min(1), location: location.optional() }).strict();
const SafetyResultSchema = z.object({ status: z.enum(["pass", "blocked", "unknown", "expired"]), findings: z.array(FindingSchema), sourcePackageIds: z.array(id), calculationVersion: id }).strict();
const DraftSchema = z.object({ formatVersion: id, missionId: id, route: RouteSchema, checks: z.array(SafetyResultSchema), transmission: z.literal("not-supported") }).strict();

function freeze<T>(value: T): T {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value as Record<string, unknown>)) freeze(child);
  }
  return value;
}

export function parseLayer(value: unknown): LayerManifest { return freeze(LayerSchema.parse(value)); }
export function parseGeoPackageManifest(value: unknown): GeoPackageManifest { return freeze(GeoPackageSchema.parse(value) as GeoPackageManifest); }
export function parseWaypoint(value: unknown): Waypoint { return freeze(WaypointSchema.parse(value)); }
export function parseRoutePlan(value: unknown): RoutePlan { return freeze(RouteSchema.parse(value)); }
export function parseGeoSafetyResult(value: unknown): GeoSafetyResult { return freeze(SafetyResultSchema.parse(value)); }
export function parseFlightPlanDraft(value: unknown): FlightPlanDraft { return freeze(DraftSchema.parse(value)); }

export interface FlightPlanDraftInput {
  missionId?: string;
  route: RoutePlan;
  checks?: readonly GeoSafetyResult[];
  formatVersion?: string;
}

export function createFlightPlanDraft(input: RoutePlan | FlightPlanDraftInput): FlightPlanDraft {
  const isInput = "route" in input;
  const route = parseRoutePlan(isInput ? input.route : input);
  const draft = {
    formatVersion: isInput ? input.formatVersion ?? "1.0" : "1.0",
    missionId: isInput ? input.missionId ?? route.id : route.id,
    route,
    checks: isInput ? input.checks ?? [] : [],
    transmission: "not-supported" as const,
  };
  return parseFlightPlanDraft(draft);
}
