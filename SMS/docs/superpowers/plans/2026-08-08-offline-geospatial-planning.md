# Offline Geospatial and Flight-Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Geospatial outputs are safety evidence and must retain datum, package, source, and freshness metadata.

**Goal:** Deliver a fully offline Colombia map and flight-planning foundation using open-source MapLibre/PMTiles terrain and vector packages plus separately controlled official aeronautical layers, with route, terrain, obstacle, airspace, weather/NOTAM, VLOS/BVLOS, and VFR/IFR checks.

**Architecture:** `@fac-isr/geo` is a pure calculation package that consumes package manifests and geometry/terrain providers. A staging packager builds signed PMTiles/MBTiles/GeoTIFF/COG/GeoJSON/KML/KMZ/GPX bundles. The console later renders local sources through MapLibre GL JS; no calculation calls a commercial tile or online geocoder.

**Tech Stack:** TypeScript strict; MapLibre GL JS; PMTiles; OpenMapTiles-compatible OSM vectors; Turf; `proj4`; `mgrs`; `geotiff`; `@turf/*`; Vitest; fast-check; fixture GeoJSON/GeoTIFF/PMTiles; no online runtime dependencies.

## Global Constraints

- Colombia-wide baseline and mission-area packages are signed and importable without internet access.
- MapLibre/PMTiles/OpenStreetMap-derived layers are open-source planning context; they cannot satisfy an official aeronautical-data gate unless approved by the competent authority.
- Terrain and obstacle checks must identify source, edition, effective period, vertical datum, horizontal datum, resolution, and freshness.
- Stored authoritative geometry is WGS 84 with explicit datum metadata; MAGNA-SIRGAS transformations are selected from an approved transformation registry.
- Aviation calculations distinguish altitude MSL from height AGL and preserve unrounded values.
- VFR/IFR, VLOS/EVLOS/BVLOS, airspace, NOTAM, and flight-plan checks return `unknown` when the required controlled layer is missing or stale.
- Flight-plan export is a draft artifact; there is no transmission or command path.

## File Map

- Create: `SMS/packages/geo/package.json`
- Create: `SMS/packages/geo/src/types.ts` — geometry, package, layer, terrain, airspace, route, weather, and plan contracts.
- Create: `SMS/packages/geo/src/coordinates.ts` — WGS 84, DMS, UTM, MGRS, and approved MAGNA-SIRGAS transformations.
- Create: `SMS/packages/geo/src/packages.ts` — manifest, signature, freshness, dependency, and downgrade checks.
- Create: `SMS/packages/geo/src/terrain.ts` — terrain/obstacle provider contract and clearance calculation.
- Create: `SMS/packages/geo/src/airspace.ts` — airspace, NOTAM, and route-intersection evaluation.
- Create: `SMS/packages/geo/src/weather.ts` — METAR, TAF, SIGMET, winds-aloft, and local-observation decoding/freshness.
- Create: `SMS/packages/geo/src/visibility.ts` — VLOS/EVLOS/BVLOS and viewshed facts.
- Create: `SMS/packages/geo/src/route.ts` — route geometry, corridors, holds, orbits, patterns, and deviations.
- Create: `SMS/packages/geo/src/flight-plan.ts` — bilingual draft flight-plan data and exports.
- Create: `SMS/packages/geo/src/index.ts`
- Create: `SMS/tools/map-packager/src/cli.ts` — connected staging packager.
- Create: `SMS/tools/map-packager/src/validate.ts` — layer/package validation.
- Test: `SMS/packages/geo/test/*.test.ts`
- Test: `SMS/tools/map-packager/test/*.test.ts`
- Create: `SMS/docs/provenance/map-package-register.jsonl`

## Interfaces

```ts
export interface GeoPackageManifest extends SignedPackageManifest {
  kind: "map" | "terrain" | "airspace" | "aip" | "notam" | "weather";
  format: "pmtiles" | "mbtiles" | "geotiff" | "cog" | "geojson" | "kml" | "kmz" | "gpx";
  horizontalDatum: "EPSG:4326" | string;
  verticalDatum?: string;
  resolution?: string;
  layers: readonly LayerManifest[];
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

export interface GeoFinding {
  code: string;
  severity: "hard" | "warning" | "information";
  messageConceptId: string;
  sourcePackageIds: readonly string[];
  location?: { lat: number; lon: number };
}

export interface TerrainSample {
  elevationMslM: number;
  horizontalAccuracyM: number;
  verticalAccuracyM: number;
  sourcePackageId: string;
  sampledAtUtc: string;
}

export interface TerrainProvider {
  sample(point: { lat: number; lon: number }): Promise<TerrainSample | null>;
  coverage(point: { lat: number; lon: number }): "covered" | "missing" | "expired";
}

export interface ViewshedResult {
  status: "pass" | "blocked" | "unknown";
  visibleFraction: number;
  sourcePackageIds: readonly string[];
  limitingPoint?: { lat: number; lon: number };
}

export interface Intersection {
  layerId: string;
  code: string;
  segmentId: string;
  startUtc?: string;
  endUtc?: string;
  sourcePackageId: string;
}

export interface NotamMatch extends Intersection {
  notamId: string;
  effectiveFromUtc: string;
  effectiveToUtc: string;
}

export interface WeatherObservation {
  id: string;
  station: string;
  observedAtUtc: string;
  source: "metar" | "taf" | "sigmet" | "winds-aloft" | "local-observation";
  visibilityM?: number;
  cloudLayers?: readonly { amount: string; baseFtAgl?: number }[];
  windKt?: { directionDeg?: number; speedKt: number; gustKt?: number };
  temperatureC?: number;
  qnhHpa?: number;
  raw: string;
  sourcePackageId: string;
  authorityClass: "official" | "approved-local-observer";
}

export interface WeatherSafetyResult {
  status: "pass" | "blocked" | "unknown" | "expired";
  observations: readonly WeatherObservation[];
  findings: readonly GeoFinding[];
  maxAgeMinutes: number;
}
```

### Task 1: Define geospatial contracts and package metadata

**Files:**
- Create: `SMS/packages/geo/package.json`
- Create: `SMS/packages/geo/src/types.ts`
- Create: `SMS/packages/geo/src/index.ts`
- Test: `SMS/packages/geo/test/contracts.test.ts`

**Interfaces:**
- Produces the `GeoPackageManifest`, `RoutePlan`, `GeoSafetyResult`, and `FlightPlanDraft` interfaces above.

- [ ] **Step 1: Write contract tests**

```ts
it("requires datum and source metadata for every layer", () => {
  expect(() => parseLayer({ ...validLayer, horizontalDatum: undefined })).toThrow("datum");
});

it("marks every flight-plan draft as non-transmittable", () => {
  expect(createFlightPlanDraft(validRoute).transmission).toBe("not-supported");
});
```

- [ ] **Step 2: Run tests to verify missing contracts fail**

Run: `cd SMS && npm test --workspace packages/geo -- contracts.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement strict schemas and source metadata**

Reject unknown formats, missing hash/signature/dependencies, unsupported coordinate units, invalid extents, and any transmission capability. Preserve layer authority separately from display style.

- [ ] **Step 4: Run tests and commit**

Run: `cd SMS && npm test --workspace packages/geo -- contracts.test.ts --run && npm run typecheck`
Expected: PASS.

```bash
git add SMS/packages/geo
git commit -m "feat(geo): define offline map and flight-plan contracts"
```

### Task 2: Implement coordinate, datum, and unit conversions

**Files:**
- Create: `SMS/packages/geo/src/coordinates.ts`
- Test: `SMS/packages/geo/test/coordinates.test.ts`
- Test: `SMS/packages/geo/test/fixtures/coordinates.json`

**Interfaces:**
- `parseCoordinate(input): Wgs84Coordinate`
- `formatDms(coordinate): DmsCoordinate`
- `toUtm(coordinate, zone): UtmCoordinate`
- `toMgrs(coordinate, precision): string`
- `transformApprovedDatum(input, transformationId): Wgs84Coordinate`
- `convertAltitude(value, from, to, terrain): number`

- [ ] **Step 1: Write round-trip and invalid-input tests**

```ts
it("round-trips decimal degrees, DMS, UTM, and MGRS within fixture tolerance", () => {
  const coordinate = fixture("bogota");
  expect(distanceM(fromMgrs(toMgrs(coordinate, 5)), coordinate)).toBeLessThan(2);
});

it("does not convert MSL to AGL without terrain elevation", () => {
  expect(() => convertAltitude(9000, "MSL", "AGL", undefined)).toThrow("terrain");
});
```

- [ ] **Step 2: Run tests to verify absent conversion functions fail**

Run: `cd SMS && npm test --workspace packages/geo -- coordinates.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement conversions with explicit metadata**

Use WGS 84 as the stored authoritative geometry. Use `proj4` and `mgrs` only with an approved transformation registry; reject an unregistered MAGNA-SIRGAS transformation. Preserve original input, parsed value, datum, units, and precision for audit.

- [ ] **Step 4: Run property tests and commit**

Run: `cd SMS && npm test --workspace packages/geo -- coordinates.test.ts --run`
Expected: PASS for Colombia fixture coordinates, hemispheres, DMS signs, UTM zones, and exact MSL/AGL requirements.

```bash
git add SMS/packages/geo/src/coordinates.ts SMS/packages/geo/test
git commit -m "feat(geo): add audited aviation coordinate conversions"
```

### Task 3: Validate and import signed offline map packages

**Files:**
- Create: `SMS/packages/geo/src/packages.ts`
- Create: `SMS/tools/map-packager/src/validate.ts`
- Create: `SMS/tools/map-packager/src/cli.ts`
- Test: `SMS/packages/geo/test/packages.test.ts`
- Test: `SMS/tools/map-packager/test/validate.test.ts`

**Interfaces:**
- `verifyGeoPackage(directory, manifest, key): VerificationReport`
- `rejectStaleOrDowngradedPackage(installed, incoming, nowUtc): void`
- CLI commands: `map-packager inspect`, `map-packager build-manifest`, `map-packager sign`, `map-packager verify`.

- [ ] **Step 1: Write package validation tests**

```ts
it.each([
  ["tampered content", tamperedPackage],
  ["unsigned manifest", unsignedPackage],
  ["expired package", expiredPackage],
  ["missing dependency", packageWithMissingDependency],
  ["unauthorized downgrade", olderPackage],
])("rejects %s", (_label, candidate) => {
  expect(verifyGeoPackage(candidate.directory, candidate.manifest, publicKey).ok).toBe(false);
});
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd SMS && npm test --workspace packages/geo -- packages.test.ts --run && npm test --workspace tools/map-packager -- validate.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement manifest and layer validation**

Validate signature, content hashes, geographic extent, coordinate/vertical datum, format, layer authority, issue/effective/expiry times, dependencies, and package version monotonicity. Mark open-source context layers separate from official aeronautical layers in the manifest.

- [ ] **Step 4: Add fixture package types and source register records**

Register a Colombia-wide OSM/OpenMapTiles-compatible PMTiles baseline, Copernicus/NASA terrain provenance, mission-area high-resolution packages, and controlled official AIP/airspace/obstacle packages. Do not download or embed copyrighted or classified content without a recorded license/use restriction.

- [ ] **Step 5: Run validation tests and commit**

Run: `cd SMS && npm test --workspace packages/geo -- packages.test.ts --run && npm test --workspace tools/map-packager -- validate.test.ts --run`
Expected: PASS; partial imports are quarantined and cannot become active.

```bash
git add SMS/packages/geo/src/packages.ts SMS/tools/map-packager SMS/packages/geo/test SMS/docs/provenance/map-package-register.jsonl
git commit -m "feat(geo): verify signed offline geospatial packages"
```

### Task 4: Implement terrain, obstacle, clearance, and viewshed calculations

**Files:**
- Create: `SMS/packages/geo/src/terrain.ts`
- Create: `SMS/packages/geo/src/visibility.ts`
- Test: `SMS/packages/geo/test/terrain.test.ts`
- Test: `SMS/packages/geo/test/visibility.test.ts`

**Interfaces:**
- `sampleTerrain(provider, coordinate): TerrainSample`
- `evaluateClearance(route, terrain, obstacles, policy): GeoSafetyResult`
- `calculateViewshed(observer, route, terrain, obstacles): ViewshedResult`
- `evaluateVisualCondition(route, requestedCondition, facts): GeoSafetyResult`

- [ ] **Step 1: Write terrain and line-of-sight tests**

```ts
it("blocks when terrain coverage does not include the route", () => {
  expect(evaluateClearance(routeOutsideTerrain, fixtureTerrain, [], policy).status).toBe("unknown");
});

it("reports the limiting obstacle and vertical reference", () => {
  const result = evaluateClearance(route, fixtureTerrain, [tower], policy);
  expect(result.findings).toContainEqual(expect.objectContaining({ code: "OBSTACLE_CLEARANCE" }));
});
```

- [ ] **Step 2: Run tests to verify missing terrain logic fails**

Run: `cd SMS && npm test --workspace packages/geo -- terrain.test.ts visibility.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement provider contracts and conservative calculations**

Sample terrain/obstacle data with explicit horizontal/vertical datums and resolution. Calculate route clearance at every segment/waypoint and return the worst point plus source package IDs. A missing or stale sample is `unknown`, not zero elevation. Viewshed and VLOS/EVLOS results include observer height, terrain assumptions, obstacle source, and calculation version.

- [ ] **Step 4: Run property tests and commit**

Run: `cd SMS && npm test --workspace packages/geo -- terrain.test.ts visibility.test.ts --run`
Expected: PASS; higher obstacles never improve clearance and degraded terrain coverage is visible.

```bash
git add SMS/packages/geo/src/terrain.ts SMS/packages/geo/src/visibility.ts SMS/packages/geo/test
git commit -m "feat(geo): evaluate terrain clearance and visual coverage"
```

### Task 5: Implement route, airspace, NOTAM, and weather intersection checks

**Files:**
- Create: `SMS/packages/geo/src/route.ts`
- Create: `SMS/packages/geo/src/airspace.ts`
- Test: `SMS/packages/geo/test/route.test.ts`
- Test: `SMS/packages/geo/test/airspace.test.ts`

**Interfaces:**
- `buildRoute(input): RoutePlan`
- `intersectRoute(route, polygonLayers): Intersection[]`
- `matchNotams(route, notams, windowUtc): NotamMatch[]`
- `evaluateRouteAirspace(input): GeoSafetyResult`

- [ ] **Step 1: Write route geometry and freshness tests**

```ts
it("detects a route intersection with a restricted area", () => {
  const result = evaluateRouteAirspace({ route, airspaces: [restrictedArea], notams: [], nowUtc });
  expect(result.status).toBe("blocked");
  expect(result.findings[0].code).toBe("AIRSPACE_CONFLICT");
});

it("does not use a stale NOTAM as current evidence", () => {
  const result = evaluateRouteAirspace({ route, airspaces: [], notams: [expiredNotam], nowUtc });
  expect(result.status).toBe("unknown");
});
```

- [ ] **Step 2: Run tests to verify missing geometry logic fails**

Run: `cd SMS && npm test --workspace packages/geo -- route.test.ts airspace.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement route builders and intersections**

Support waypoints, corridors, holds, orbits, area-search patterns, emergency/alternate/forced-recovery sites, altitude profiles, and approved deviation limits. Use geodesic distance and stable segment IDs; preserve original draw inputs.

- [ ] **Step 4: Implement time/space matching for airspace and NOTAM**

Match route geometry, altitude band, and mission time against airspace, AIP, official obstacles, and NOTAM effective windows. Open-source overlays are advisory unless the layer authority is approved. Missing required official coverage returns `unknown`.

- [ ] **Step 5: Run tests and commit**

Run: `cd SMS && npm test --workspace packages/geo -- route.test.ts airspace.test.ts --run`
Expected: PASS for conflicts, no-conflict, stale, missing, boundary-touch, and altitude/time-window fixtures.

```bash
git add SMS/packages/geo/src/route.ts SMS/packages/geo/src/airspace.ts SMS/packages/geo/test
git commit -m "feat(geo): validate route airspace and NOTAM intersections"
```

### Task 6: Implement weather decoding, matching, and freshness gates

**Files:**
- Create: `SMS/packages/geo/src/weather.ts`
- Test: `SMS/packages/geo/test/weather.test.ts`
- Test: `SMS/packages/geo/test/fixtures/weather.json`

**Interfaces:**
- `decodeMetar(raw, sourcePackageId): WeatherObservation`
- `decodeTaf(raw, sourcePackageId): WeatherObservation`
- `decodeSigmet(raw, sourcePackageId): WeatherObservation`
- `validateWeatherForRoute(input): WeatherSafetyResult`

- [ ] **Step 1: Write decoder and freshness tests**

```ts
it("decodes METAR wind, visibility, clouds, temperature, and QNH in UTC", () => {
  const observation = decodeMetar(fixtureMetar, "weather-pkg-1");
  expect(observation.source).toBe("metar");
  expect(observation.windKt?.speedKt).toBeGreaterThan(0);
  expect(observation.sourcePackageId).toBe("weather-pkg-1");
});

it("blocks when a critical weather observation is stale", () => {
  const result = validateWeatherForRoute({ ...weatherInput, nowUtc: "2026-08-08T18:00:00Z" });
  expect(result.status).toBe("expired");
});
```

- [ ] **Step 2: Run tests to verify weather support is absent**

Run: `cd SMS && npm test --workspace packages/geo -- weather.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement source-preserving aviation weather decoders**

Decode METAR/TAF/SIGMET and winds-aloft packages while retaining the raw string, station, issue/observation/validity times, source authority, units, and parse warnings. Local manual observations require observer identity, location, UTC time, and approved source status.

- [ ] **Step 4: Implement route/time/limit matching**

Match visibility, cloud clearance, wind/crosswind, temperature, precipitation, density altitude, and policy limits to the route/aircraft/flight rule. Missing, malformed, or conflicting critical weather returns `unknown`; stale data returns `expired`; a controlled exception follows P1 rather than silently passing.

- [ ] **Step 5: Run tests and commit**

Run: `cd SMS && npm test --workspace packages/geo -- weather.test.ts --run`
Expected: PASS for valid/invalid/stale METAR, TAF, SIGMET, winds-aloft, and local-observation fixtures.

```bash
git add SMS/packages/geo/src/weather.ts SMS/packages/geo/test
git commit -m "feat(geo): decode weather and enforce freshness"
```

### Task 7: Implement VFR/IFR and flight-plan drafting without transmission

**Files:**
- Create: `SMS/packages/geo/src/flight-plan.ts`
- Test: `SMS/packages/geo/test/flight-plan.test.ts`
- Create: `SMS/docs/provenance/flight-plan-format.md`

**Interfaces:**
- `evaluateFlightRules(input): GeoSafetyResult`
- `createFlightPlanDraft(input): FlightPlanDraft`
- `exportDraft(draft, format): Uint8Array | string`

- [ ] **Step 1: Write VFR/IFR gating and export tests**

```ts
it("blocks IFR for a class IA aircraft", () => {
  expect(evaluateFlightRules({ ...validFacts, aircraftClass: "IA", flightRule: "IFR" }).status).toBe("blocked");
});

it("requires an approved authorization and segregated airspace for IC IFR", () => {
  expect(evaluateFlightRules({ ...icFacts, ifrAuthorization: undefined }).status).toBe("unknown");
});

it("exports a draft with no transmission operation", () => {
  const draft = createFlightPlanDraft(validDraftInput);
  expect(draft.transmission).toBe("not-supported");
  expect(JSON.stringify(draft)).not.toMatch(/send|transmit|command/i);
});
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd SMS && npm test --workspace packages/geo -- flight-plan.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement class/capability/airspace-gated VFR/IFR evaluation**

Use P1 rule facts for RACAE applicability. For IFR, require the approved class/capability predicate, segregated-airspace fact where required, equipment/integrity evidence, and authorization; never infer authorization from a map layer.

- [ ] **Step 4: Implement bilingual JSON, GeoJSON, KML/KMZ, GPX, and human-readable draft exports**

Include mission/revision ID, source package IDs, route, datum, altitude reference, checks, warnings, and `transmission: not-supported`. Do not include any API route or adapter that could transmit the draft.

- [ ] **Step 5: Run tests and commit**

Run: `cd SMS && npm test --workspace packages/geo -- flight-plan.test.ts --run`
Expected: PASS; export round-trips preserve geometry and safety status.

```bash
git add SMS/packages/geo/src/flight-plan.ts SMS/packages/geo/test SMS/docs/provenance/flight-plan-format.md
git commit -m "feat(geo): draft bilingual non-transmittable flight plans"
```

## P3 Completion Evidence

P3 is complete when a disconnected fixture workstation can import signed local layers, render and calculate with WGS 84/approved transformations, decode and freshness-check METAR/TAF/SIGMET/local observations, identify terrain/obstacle/airspace/NOTAM conflicts, evaluate VLOS/EVLOS/BVLOS and VFR/IFR conditions, and export a signed-reference draft that explicitly cannot be transmitted.
