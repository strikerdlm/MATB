# Fleet, Maintenance, Capability, and Energy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Fleet and energy results are safety inputs; no marketing claim may become an operational capability without evidence.

**Goal:** Provide vendor-neutral aircraft, GCS, payload, battery, maintenance, airworthiness, qualification, and energy models that feed the safety kernel with auditable facts and conservative reserve calculations.

**Architecture:** A pure `@fac-isr/fleet` package models configuration and releases; a pure `@fac-isr/energy` package calculates segment demand and reserves from approved evidence. Persistence adapters are added by the edge service later. Capability claims carry their evidence and confidence; unsupported or uncertain values produce explicit blockers rather than optimistic defaults.

**Tech Stack:** TypeScript strict; Zod; `@fac-isr/evidence`; `@fac-isr/safety-kernel`; Vitest; fast-check; units represented as branded SI values with aviation display conversions.

## Global Constraints

- Support unarmed ISR and support configurations across every RACAE class; armed and strike configurations remain blocked.
- Capability claims are vendor-neutral and source-backed; vendor marketing material is marked vendor-claimed and cannot satisfy airworthiness or release evidence by itself.
- Battery reserve is calculated from aircraft, payload, environment, route segments, health, and model uncertainty; in-flight estimates never lower the approved minimum reserve.
- Maintenance release is a separate four-gate role and includes aircraft identity/configuration, discrepancies, inspection, minimum equipment, battery, payload, software, and return-to-service authority.
- Operational crew data stores only the minimum qualification, recency, assignment, duty, and safety-status data; clinical diagnoses are not represented.
- No method, field, event, or adapter in this plan may send a command to a GCS or aircraft.

## File Map

- Create: `SMS/packages/fleet/package.json`
- Create: `SMS/packages/fleet/src/types.ts` — aircraft, GCS, payload, capability, maintenance, qualification, and battery contracts.
- Create: `SMS/packages/fleet/src/configuration.ts` — configuration compatibility and armed/strike block.
- Create: `SMS/packages/fleet/src/maintenance.ts` — discrepancies, inspection, airworthiness, minimum equipment, and release predicates.
- Create: `SMS/packages/fleet/src/qualification.ts` — role, recency, duty, and assignment checks.
- Create: `SMS/packages/fleet/src/index.ts`
- Create: `SMS/packages/energy/package.json`
- Create: `SMS/packages/energy/src/types.ts` — energy input/result and uncertainty contracts.
- Create: `SMS/packages/energy/src/model.ts` — deterministic segment and reserve calculation.
- Create: `SMS/packages/energy/src/index.ts`
- Test: `SMS/packages/fleet/test/*.test.ts`
- Test: `SMS/packages/energy/test/*.test.ts`
- Create: `SMS/docs/provenance/capability-evidence-register.jsonl`

## Interfaces

```ts
export interface UASSystem {
  id: string;
  manufacturer: string;
  model: string;
  aircraftClass: AircraftClass;
  mtowKg: number;
  configuration: "unarmed-isr" | "unarmed-support" | "armed" | "strike";
  approvedConfigurationId: string;
}

export interface CapabilityClaim {
  id: string;
  subjectId: string;
  capability: "vfr" | "ifr" | "vlos" | "evlos" | "bvlos" | "daa" | "c2" | "gnss-integrity" | "payload";
  value: string | number | boolean;
  units?: string;
  operatingConditions: Record<string, string | number | boolean>;
  evidenceRefs: string[];
  confidence: "verified" | "qualified" | "vendor-claimed" | "research-only";
  validFromUtc: string;
  validToUtc?: string;
}

export interface MaintenanceRelease {
  aircraftId: string;
  configurationHash: string;
  inspectionDueAtUtc: string;
  openDiscrepancies: readonly Discrepancy[];
  minimumEquipmentSatisfied: boolean;
  batteryRelease: "released" | "restricted" | "quarantined";
  payloadRelease: "released" | "restricted" | "removed";
  softwareBaseline: string;
  authorizedBy: string;
  decision: "released" | "blocked";
  signedAtUtc: string;
}

export interface EnergyModelInput {
  aircraftId: string;
  battery: BatteryState;
  segments: readonly EnergySegment[];
  weather: { windKt: number; temperatureC: number; densityAltitudeFt?: number };
  payloadMassKg: number;
  approvedReserve: ReservePolicy;
  modelVersion: string;
}

export interface EnergyModelResult {
  segmentResults: readonly SegmentEnergyResult[];
  predictedAtRecoveryPercent: number;
  diversionReservePercent: number;
  contingencyReservePercent: number;
  uncertaintyPercent: number;
  limitingAssumption: string;
  status: "pass" | "blocked" | "unknown";
}

export interface BatteryState {
  serialNumber: string;
  aircraftCompatibility: readonly string[];
  chemistry: string;
  nominalCapacityWh: number;
  cycles: number;
  ageDays: number;
  stateOfChargePercent: number;
  stateOfHealthPercent: number;
  cellImbalanceMv?: number;
  internalResistanceMohm?: number;
  temperatureC?: number;
  status: "released" | "restricted" | "quarantined";
}

export interface EnergySegment {
  id: string;
  kind: "climb" | "cruise" | "work" | "hold" | "return" | "diversion" | "contingency";
  distanceNm: number;
  durationMinutes?: number;
  altitudeChangeFt?: number;
  expectedGroundspeedKt?: number;
  payloadPowerW?: number;
}

export interface ReservePolicy {
  recoveryMinimumPercent: number;
  diversionMinimumPercent: number;
  contingencyMinimumPercent: number;
  uncertaintyMethod: "approved-model";
}

export interface SegmentEnergyResult {
  segmentId: string;
  demandPercent: number;
  remainingPercent: number;
  uncertaintyPercent: number;
  limitingAssumption?: string;
}

export interface Discrepancy {
  id: string;
  description: string;
  severity: "minor" | "major" | "critical";
  disposition: "open" | "approved-deferred" | "resolved";
  evidenceRefs: readonly string[];
}

export interface ConfigurationResult {
  status: "pass" | "blocked" | "unknown";
  reasons: readonly string[];
  evidenceRefs: readonly string[];
}

export interface CapabilityResult {
  status: "pass" | "blocked" | "unknown";
  reason: string;
  evidenceRefs: readonly string[];
}

export interface MaintenanceEvaluation {
  status: "pass" | "blocked" | "unknown";
  blockers: readonly string[];
  evidenceRefs: readonly string[];
}

export interface CrewEvaluation {
  status: "pass" | "blocked" | "unknown";
  blockers: readonly string[];
  evidenceRefs: readonly string[];
}

export interface DutyEvaluation {
  status: "pass" | "restricted" | "blocked" | "unknown";
  reason: string;
  evidenceRefs: readonly string[];
}
```

### Task 1: Define fleet and battery contracts

**Files:**
- Create: `SMS/packages/fleet/package.json`
- Create: `SMS/packages/fleet/src/types.ts`
- Create: `SMS/packages/energy/package.json`
- Create: `SMS/packages/energy/src/types.ts`
- Test: `SMS/packages/fleet/test/contracts.test.ts`
- Test: `SMS/packages/energy/test/contracts.test.ts`

**Interfaces:**
- Consumes: `AircraftClass` and branded IDs from `@fac-isr/safety-kernel`.
- Produces: the fleet and energy interfaces above.

- [ ] **Step 1: Write contract tests for valid and invalid quantities**

```ts
it("rejects a battery with negative cycles or state of health above 100%", () => {
  expect(() => parseBattery({ ...validBattery, cycles: -1 })).toThrow();
  expect(() => parseBattery({ ...validBattery, stateOfHealthPercent: 101 })).toThrow();
});

it("requires evidence for a non-research capability claim", () => {
  expect(() => parseCapability({ ...validClaim, evidenceRefs: [] })).toThrow("evidence");
});
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `cd SMS && npm test --workspace packages/fleet -- contracts.test.ts --run && npm test --workspace packages/energy -- contracts.test.ts --run`
Expected: FAIL because the packages and parsers are absent.

- [ ] **Step 3: Implement strict schemas and branded quantities**

Reject NaN, infinity, negative mass/energy, invalid serials, empty evidence arrays for verified/qualified claims, unknown class strings, and local-time timestamps. Preserve raw manufacturer values separately from normalized SI values.

- [ ] **Step 4: Run tests and typecheck**

Run: `cd SMS && npm test --workspace packages/fleet -- contracts.test.ts --run && npm test --workspace packages/energy -- contracts.test.ts --run && npm run typecheck`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add SMS/packages/fleet SMS/packages/energy
git commit -m "feat(fleet): define auditable aircraft and energy contracts"
```

### Task 2: Implement configuration compatibility and capability evidence

**Files:**
- Create: `SMS/packages/fleet/src/configuration.ts`
- Create: `SMS/packages/fleet/src/capabilities.ts`
- Test: `SMS/packages/fleet/test/configuration.test.ts`
- Test: `SMS/packages/fleet/test/capabilities.test.ts`
- Modify: `SMS/docs/provenance/capability-evidence-register.jsonl`

**Interfaces:**
- `evaluateConfiguration(system, payload, gcs): ConfigurationResult`
- `evaluateCapability(claim, requiredCondition, evidenceSnapshot): CapabilityResult`
- `compareCapabilityBaselines(records): CapabilityComparison`

- [ ] **Step 1: Write configuration and evidence tests**

```ts
it("hard-blocks armed and strike configurations", () => {
  expect(evaluateConfiguration(armedSystem, payload, gcs).status).toBe("blocked");
});

it("does not treat vendor-claimed IFR capability as approved", () => {
  expect(evaluateCapability(vendorClaim, ifrCondition, snapshot).status).toBe("unknown");
});
```

- [ ] **Step 2: Run tests to verify missing implementation fails**

Run: `cd SMS && npm test --workspace packages/fleet -- configuration.test.ts capabilities.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement compatibility and confidence rules**

Require compatible aircraft/GCS/payload/battery IDs, approved software baseline, payload mass/power/thermal limits, and configuration hash. `verified` and `qualified` claims may satisfy configured conditions; `vendor-claimed` requires explicit evidence review and cannot satisfy airworthiness, IFR, BVLOS, or release hard requirements; `research-only` is never operational evidence.

- [ ] **Step 4: Add public comparison records without protected or weapon data**

Register publicly documented DJI Enterprise and non-weaponized military references with source URL, retrieval date, claim confidence, licensing, and comparison scope. Keep the matrix vendor-neutral and exclude imagery, intelligence, weapons, targeting, and classified content.

- [ ] **Step 5: Run tests and commit**

Run: `cd SMS && npm test --workspace packages/fleet -- configuration.test.ts capabilities.test.ts --run`
Expected: PASS.

```bash
git add SMS/packages/fleet SMS/docs/provenance/capability-evidence-register.jsonl
git commit -m "feat(fleet): gate capabilities by approved evidence"
```

### Task 3: Implement maintenance and return-to-service predicates

**Files:**
- Create: `SMS/packages/fleet/src/maintenance.ts`
- Test: `SMS/packages/fleet/test/maintenance.test.ts`

**Interfaces:**
- `evaluateMaintenanceRelease(input): MaintenanceEvaluation`
- `isMinimumEquipmentSatisfied(input): boolean`
- `classifyDiscrepancy(discrepancy, approvedDeferrals): "open" | "deferred" | "blocking"`

- [ ] **Step 1: Write maintenance blocker tests**

```ts
it.each([
  ["inspection overdue", { inspectionDueAtUtc: "2026-08-01T00:00:00Z" }],
  ["quarantined battery", { batteryRelease: "quarantined" }],
  ["missing return-to-service authority", { authorizedBy: "" }],
  ["unresolved blocking discrepancy", { openDiscrepancies: [blockingDiscrepancy] }],
])("blocks maintenance release for %s", (_label, change) => {
  expect(evaluateMaintenanceRelease({ ...validMaintenanceInput, release: { ...validRelease, ...change }, nowUtc }).status)
    .toBe("blocked");
});
```

- [ ] **Step 2: Run tests to verify missing predicates fail**

Run: `cd SMS && npm test --workspace packages/fleet -- maintenance.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement maintenance evidence checks**

Check identity/configuration hash, inspection and airworthiness dates, minimum equipment, open discrepancies and approved deferrals, battery/payload release, approved firmware/software baseline, and authorized return-to-service signature. A restriction must be visible to the safety kernel and cannot be silently ignored.

- [ ] **Step 4: Run tests and commit**

Run: `cd SMS && npm test --workspace packages/fleet -- maintenance.test.ts --run`
Expected: PASS.

```bash
git add SMS/packages/fleet/src/maintenance.ts SMS/packages/fleet/test/maintenance.test.ts
git commit -m "feat(fleet): enforce maintenance release evidence"
```

### Task 4: Implement crew qualification, recency, duty, and assignment checks

**Files:**
- Create: `SMS/packages/fleet/src/qualification.ts`
- Test: `SMS/packages/fleet/test/qualification.test.ts`

**Interfaces:**
- `evaluateCrewAssignment(input): CrewEvaluation`
- `evaluateDutyAndRest(dutyPeriod, policy, nowUtc): DutyEvaluation`
- `requireOneOperatorPerAircraft(assignments): SafetyBlocker[]`

- [ ] **Step 1: Write qualification and staffing tests**

```ts
it("requires an independent qualified operator for each active aircraft", () => {
  expect(requireOneOperatorPerAircraft([
    { aircraftId: "A-1", role: "operator", userId: "U-1", qualified: true },
    { aircraftId: "A-2", role: "operator", userId: "U-1", qualified: true },
  ])).toContainEqual(expect.objectContaining({ code: "OPERATOR_ASSIGNED_TO_MULTIPLE_AIRCRAFT" }));
});

it("does not expose medical diagnosis in operational output", () => {
  const result = evaluateCrewAssignment(inputWithMedicalNote);
  expect(JSON.stringify(result)).not.toContain("diagnosis");
});
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd SMS && npm test --workspace packages/fleet -- qualification.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement qualifications and privacy-minimized duty checks**

Validate role, aircraft assignment, qualification edition, recency, expiry, duty/rest windows, cumulative workload, screen exposure, and self-declared operational safety status. Return only `available`, `restricted`, `unavailable`, or `unknown` plus evidence references; do not accept diagnosis or clinical reasoning fields.

- [ ] **Step 4: Run property tests for duplicate assignments and expiry**

Run: `cd SMS && npm test --workspace packages/fleet -- qualification.test.ts --run`
Expected: PASS at exact qualification/duty expiry boundaries and for every duplicate operator assignment.

- [ ] **Step 5: Commit**

```bash
git add SMS/packages/fleet/src/qualification.ts SMS/packages/fleet/test/qualification.test.ts
git commit -m "feat(fleet): enforce crew qualification and staffing"
```

### Task 5: Implement deterministic segment energy and reserve calculations

**Files:**
- Create: `SMS/packages/energy/src/model.ts`
- Modify: `SMS/packages/energy/src/index.ts`
- Test: `SMS/packages/energy/test/model.test.ts`
- Test: `SMS/packages/energy/test/property.test.ts`

**Interfaces:**
- `calculateMissionEnergy(input): EnergyModelResult`
- `updateReadOnlyEstimate(previous, telemetry): EnergyModelResult`
- `assertReserveNeverDecreases(approved, estimate): void`

- [ ] **Step 1: Write failing segment and reserve tests**

```ts
it("reports predicted energy at every waypoint and reserve segments", () => {
  const result = calculateMissionEnergy(validEnergyInput);
  expect(result.segmentResults).toHaveLength(validEnergyInput.segments.length);
  expect(result.predictedAtRecoveryPercent).toBeGreaterThanOrEqual(0);
  expect(result.contingencyReservePercent).toBeGreaterThan(0);
});

it("blocks when payload, wind, battery health, or model evidence is unknown", () => {
  expect(calculateMissionEnergy({ ...validEnergyInput, payloadMassKg: NaN }).status).toBe("unknown");
});

it("never lowers the approved minimum from read-only telemetry", () => {
  expect(() => assertReserveNeverDecreases(approvedResult, telemetryEstimateBelowReserve)).toThrow("approved reserve");
});
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd SMS && npm test --workspace packages/energy -- model.test.ts property.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement the model with explicit assumptions**

Calculate climb, cruise, work, hold, return, diversion, and contingency segments from approved performance evidence, expected groundspeed, wind, temperature/density altitude, payload mass/power, battery state of health, and uncertainty. Preserve unrounded internal values and report display units separately. If any limiting input is unknown, return `unknown` and the exact limiting assumption.

- [ ] **Step 4: Add monotonic property tests**

Use fast-check to prove that greater payload, stronger adverse wind, lower state of health, or longer route cannot improve the predicted reserve under the same model. Test unit conversion and floating-point boundary behavior.

- [ ] **Step 5: Run tests and commit**

Run: `cd SMS && npm test --workspace packages/energy -- model.test.ts property.test.ts --run`
Expected: PASS; every result includes model version, input snapshot hash, uncertainty, and limiting assumption.

```bash
git add SMS/packages/energy/src SMS/packages/energy/test
git commit -m "feat(energy): calculate auditable aircraft reserves"
```

### Task 6: Connect fleet and energy results to the safety kernel

**Files:**
- Modify: `SMS/packages/safety-kernel/src/types.ts`
- Modify: `SMS/packages/safety-kernel/src/evaluate.ts`
- Create: `SMS/packages/safety-kernel/src/fleet-inputs.ts`
- Test: `SMS/packages/safety-kernel/test/fleet-energy-integration.test.ts`

**Interfaces:**
- `buildFleetSafetyFacts(fleet, maintenance, crew, energy): FleetSafetyFacts`
- `evaluateMission` consumes `FleetSafetyFacts` and adds traceable blockers.

- [ ] **Step 1: Write integration tests**

```ts
it("blocks release for insufficient reserve and links the energy evidence", () => {
  const result = evaluateMission(inputWithEnergyResult({ status: "blocked" }));
  expect(result.blockers).toContainEqual(expect.objectContaining({ code: "INSUFFICIENT_RESERVE" }));
  expect(result.evaluations.find(({ requirementId }) => requirementId === "energy.reserve")?.evidenceRefs)
    .toContain("energy-model-fixture-1");
});
```

- [ ] **Step 2: Run test to verify the integration is absent**

Run: `cd SMS && npm test --workspace packages/safety-kernel -- fleet-energy-integration.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement the adapter without duplicating calculations**

Pass normalized maintenance, qualification, capability, battery, and energy results into the kernel as facts. The kernel decides applicability and release status; fleet/energy packages do not approve missions themselves.

- [ ] **Step 4: Run cross-package tests and commit**

Run: `cd SMS && npm test --workspaces -- --run && npm run typecheck`
Expected: PASS.

```bash
git add SMS/packages/safety-kernel SMS/packages/fleet SMS/packages/energy
git commit -m "feat(safety-kernel): consume fleet and energy evidence"
```

## P2 Completion Evidence

P2 is complete when aircraft class/configuration, capability claims, maintenance releases, crew assignments, batteries, and energy reserves are independently testable, source-backed, privacy-minimized, and consumed by P1 with explicit blockers for uncertainty or insufficiency.
