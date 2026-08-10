/// <reference path="./external.d.ts" />

import mgrs from "mgrs";
import proj4 from "proj4";

export interface Wgs84Coordinate {
  lat: number;
  lon: number;
  datum: "EPSG:4326";
}

export interface DmsValue {
  degrees: number;
  minutes: number;
  seconds: number;
  hemisphere: "N" | "S" | "E" | "W";
}

export interface DmsCoordinate {
  latitude: DmsValue;
  longitude: DmsValue;
  datum: "EPSG:4326";
}

export interface UtmCoordinate {
  easting: number;
  northing: number;
  zone: number;
  hemisphere: "N" | "S";
  datum: "EPSG:4326";
}

export interface ProjectedCoordinate {
  easting: number;
  northing: number;
  datum: "EPSG:3116";
}

export type DatumCoordinateInput = Wgs84Coordinate | ProjectedCoordinate;
export type AltitudeReference = "MSL" | "AGL";

export interface TerrainElevation {
  elevationMslM: number;
}

export const APPROVED_TRANSFORMATIONS = Object.freeze({
  "EPSG:4326-identity": Object.freeze({ sourceDatum: "EPSG:4326", targetDatum: "EPSG:4326" }),
  "EPSG:3116-to-EPSG:4326": Object.freeze({ sourceDatum: "EPSG:3116", targetDatum: "EPSG:4326" }),
});

const WGS84 = "EPSG:4326";
const MGRS_PRECISION_MIN = 1;
const MGRS_PRECISION_MAX = 5;
const EARTH_RADIUS_M = 6_378_137;
const EPSG_3116 = "+proj=tmerc +lat_0=4.596200416666666 +lon_0=-74.07750791666666 +k=0.9992 +x_0=1000000 +y_0=1000000 +ellps=GRS80 +units=m +no_defs";

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function assertLatitude(value: number): void {
  if (!finite(value) || value < -90 || value > 90) throw new RangeError("latitude must be between -90 and 90 degrees");
}

function assertLongitude(value: number): void {
  if (!finite(value) || value < -180 || value > 180) throw new RangeError("longitude must be between -180 and 180 degrees");
}

export function parseCoordinate(input: { lat: number; lon: number; datum?: string; units?: string }): Wgs84Coordinate {
  if (input === null || typeof input !== "object") throw new TypeError("coordinate must be an object");
  if (input.datum !== undefined && input.datum !== WGS84) throw new RangeError("coordinate datum must be WGS 84 EPSG:4326");
  if (input.units !== undefined && input.units !== "degrees") throw new RangeError("coordinate units must be decimal degrees");
  assertLatitude(input.lat);
  assertLongitude(input.lon);
  return Object.freeze({ lat: input.lat, lon: input.lon, datum: WGS84 });
}

function dmsValue(value: number, positive: "N" | "E", negative: "S" | "W"): DmsValue {
  const hemisphere = value < 0 ? negative : positive;
  const absolute = Math.abs(value);
  let degrees = Math.floor(absolute);
  const minutesFloat = (absolute - degrees) * 60;
  let minutes = Math.floor(minutesFloat);
  let seconds = (minutesFloat - minutes) * 60;
  if (seconds >= 59.9999999995) {
    seconds = 0;
    minutes += 1;
  }
  if (minutes >= 60) {
    minutes = 0;
    degrees += 1;
  }
  return Object.freeze({ degrees, minutes, seconds, hemisphere });
}

export function formatDms(coordinate: Wgs84Coordinate): DmsCoordinate {
  const parsed = parseCoordinate(coordinate);
  return Object.freeze({ latitude: dmsValue(parsed.lat, "N", "S"), longitude: dmsValue(parsed.lon, "E", "W"), datum: WGS84 });
}

function signedDms(value: DmsValue, axis: "latitude" | "longitude"): number {
  const maxDegrees = axis === "latitude" ? 90 : 180;
  if (!Number.isInteger(value.degrees) || value.degrees < 0 || value.degrees > maxDegrees) throw new RangeError(`${axis} degrees are invalid`);
  if (!Number.isInteger(value.minutes) || value.minutes < 0 || value.minutes >= 60 || !finite(value.seconds) || value.seconds < 0 || value.seconds >= 60) throw new RangeError(`${axis} DMS components are invalid`);
  const expectedHemisphere = axis === "latitude" ? ["N", "S"] : ["E", "W"];
  if (!expectedHemisphere.includes(value.hemisphere)) throw new RangeError(`${axis} hemisphere is invalid`);
  if (value.degrees === maxDegrees && (value.minutes > 0 || value.seconds > 0)) throw new RangeError(`${axis} exceeds its limit`);
  const sign = value.hemisphere === "S" || value.hemisphere === "W" ? -1 : 1;
  return sign * (value.degrees + value.minutes / 60 + value.seconds / 3600);
}

export function parseDms(input: DmsCoordinate): Wgs84Coordinate {
  if (input.datum !== WGS84) throw new RangeError("DMS datum must be WGS 84 EPSG:4326");
  return parseCoordinate({ lat: signedDms(input.latitude, "latitude"), lon: signedDms(input.longitude, "longitude"), datum: WGS84 });
}

function assertZone(zone: number): void {
  if (!Number.isInteger(zone) || zone < 1 || zone > 60) throw new RangeError("UTM zone must be an integer from 1 to 60");
}

function utmDefinition(zone: number, south = false): string {
  assertZone(zone);
  return `+proj=utm +zone=${zone} +datum=WGS84 +units=m +no_defs${south ? " +south" : ""}`;
}

export function toUtm(coordinate: Wgs84Coordinate, zone: number): UtmCoordinate {
  const parsed = parseCoordinate(coordinate);
  assertZone(zone);
  const [easting, northing] = proj4(WGS84, utmDefinition(zone, parsed.lat < 0), [parsed.lon, parsed.lat]);
  return Object.freeze({ easting, northing, zone, hemisphere: parsed.lat < 0 ? "S" : "N", datum: WGS84 });
}

export function fromUtm(coordinate: UtmCoordinate): Wgs84Coordinate {
  assertZone(coordinate.zone);
  if (!finite(coordinate.easting) || !finite(coordinate.northing) || coordinate.easting < 100_000 || coordinate.easting > 900_000 || coordinate.northing < 0 || coordinate.northing > 10_000_000) throw new RangeError("UTM coordinates are invalid");
  if (coordinate.hemisphere !== "N" && coordinate.hemisphere !== "S") throw new RangeError("UTM hemisphere is invalid");
  const [lon, lat] = proj4(utmDefinition(coordinate.zone, coordinate.hemisphere === "S"), WGS84, [coordinate.easting, coordinate.northing]);
  return parseCoordinate({ lat, lon, datum: WGS84 });
}

export function toMgrs(coordinate: Wgs84Coordinate, precision: number): string {
  const parsed = parseCoordinate(coordinate);
  if (!Number.isInteger(precision) || precision < MGRS_PRECISION_MIN || precision > MGRS_PRECISION_MAX) throw new RangeError("MGRS precision must be an integer from 1 to 5");
  return mgrs.forward([parsed.lon, parsed.lat], precision);
}

export function fromMgrs(value: string): Wgs84Coordinate {
  if (typeof value !== "string" || !/^[0-9]{1,2}[C-HJ-NP-X][A-HJ-NP-Z]{2}\d{2,10}$/i.test(value.trim())) throw new RangeError("MGRS coordinate is invalid");
  const [lon, lat] = mgrs.toPoint(value.trim().toUpperCase());
  return parseCoordinate({ lat, lon, datum: WGS84 });
}

export function transformApprovedDatum(input: DatumCoordinateInput, transformationId: string): Wgs84Coordinate {
  const transformation = APPROVED_TRANSFORMATIONS[transformationId as keyof typeof APPROVED_TRANSFORMATIONS];
  if (transformation === undefined) throw new RangeError("datum transformation is not approved");
  if (input.datum !== transformation.sourceDatum) throw new RangeError("coordinate datum does not match approved transformation");
  if (transformationId === "EPSG:4326-identity") return parseCoordinate(input as Wgs84Coordinate);
  const projected = input as ProjectedCoordinate;
  if (!finite(projected.easting) || !finite(projected.northing)) throw new RangeError("projected coordinate is invalid");
  const [lon, lat] = proj4(EPSG_3116, WGS84, [projected.easting, projected.northing]);
  return parseCoordinate({ lat, lon, datum: WGS84 });
}

export function convertAltitude(value: number, from: AltitudeReference, to: AltitudeReference, terrain: TerrainElevation | undefined): number {
  if (!finite(value)) throw new RangeError("altitude must be finite");
  if (from !== "MSL" && from !== "AGL") throw new RangeError("altitude reference is invalid");
  if (to !== "MSL" && to !== "AGL") throw new RangeError("altitude reference is invalid");
  if (from === to) return value;
  if (terrain === undefined || !finite(terrain.elevationMslM)) throw new Error("terrain elevation is required for MSL/AGL conversion");
  return from === "MSL" ? value - terrain.elevationMslM : value + terrain.elevationMslM;
}

export function distanceM(left: Wgs84Coordinate, right: Wgs84Coordinate): number {
  const a = parseCoordinate(left);
  const b = parseCoordinate(right);
  const toRadians = (value: number): number => value * Math.PI / 180;
  const deltaLat = toRadians(b.lat - a.lat);
  const deltaLon = toRadians(b.lon - a.lon);
  const haversine = Math.sin(deltaLat / 2) ** 2 + Math.cos(toRadians(a.lat)) * Math.cos(toRadians(b.lat)) * Math.sin(deltaLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(haversine));
}
