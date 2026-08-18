# Safety Kernel and Four-Gate Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. The kernel must be tested independently of the UI and API.

**Goal:** Implement a deterministic, bilingual safety kernel that evaluates RACAE applicability, risk, data freshness, mission lifecycle, material-change dependencies, and four-gate release without ever producing a ready result from unknown or unapproved evidence.

**Architecture:** Pure TypeScript functions consume a frozen mission revision, signed evidence/policy snapshots, fleet/crew facts, geospatial facts, and weather/NOTAM snapshots. The kernel returns immutable explanations and blockers; an API may persist and display those results but cannot alter the evaluation semantics. A missing active policy package deliberately blocks release.

**Tech Stack:** TypeScript strict; `@fac-isr/evidence`; Zod; Vitest; fast-check; immutable DTOs; UTC ISO-8601 timestamps; no database, browser, filesystem, or network dependency in the kernel.

## Global Constraints

- RACAE 94 section 94.201(a) is enforced as one qualified operator or remote pilot per active aircraft.
- RACAE 94 section 94.250 swarm operations are research-only and non-dispatchable in the first operational profile.
- RACAE 94 section 94.155 autonomous operation is blocked; supervised automation is permitted only when the approved rule package says the human can supervise and intervene.
- Armed, strike, weapon-carrying, or weapon-employment configurations are always hard-blocked in the State Aviation operational profile.
- All RACAE aircraft classes are represented: IA `15 g–<7 kg`, IB `7–<15 kg`, IC `15–<150 kg`, II `>150–600 kg`, III `>600 kg`.
- IFR is not implied by class alone; the applicable approved rule package must confirm class, segregated airspace, aircraft equipment, and authorization.
- The engine starts from an approved FAC policy package containing the risk matrix, NASO thresholds, delegated authorities, and checklist predicates; an absent or draft policy package blocks dependent gates.
- Rule results are `pass`, `fail`, `unknown`, `expired`, or `not-reviewed`; an unknown hard rule cannot be interpreted as pass.
- The kernel is deterministic for fixed inputs, versioned, and locale-independent.

## File Map

- Create: `SMS/packages/safety-kernel/package.json`
- Create: `SMS/packages/safety-kernel/src/types.ts` — mission, policy, rule, gate, risk, and blocker contracts.
- Create: `SMS/packages/safety-kernel/src/applicability.ts` — class, operation, crew, airspace, and configuration predicates.
- Create: `SMS/packages/safety-kernel/src/evaluate.ts` — deterministic rule evaluation and explanation assembly.
- Create: `SMS/packages/safety-kernel/src/lifecycle.ts` — mission state transition and material-change rules.
- Create: `SMS/packages/safety-kernel/src/dependencies.ts` — field-to-evaluation/gate dependency graph.
- Create: `SMS/packages/safety-kernel/src/risk.ts` — approved matrix, NASO, residual risk, and exception evaluation.
- Create: `SMS/packages/safety-kernel/src/gates.ts` — four-gate workflow and approval invalidation.
- Create: `SMS/packages/safety-kernel/src/terminology.ts` — stable concept IDs consumed by locale renderers.
- Create: `SMS/packages/safety-kernel/src/index.ts` — public API.
- Create: `SMS/packages/safety-kernel/test/*.test.ts` — unit, property, and golden blocked cases.
- Create: `SMS/packages/safety-kernel/test/fixtures/*.json` — all-class and negative mission fixtures.

## Interfaces

```ts
export type AircraftClass = "IA" | "IB" | "IC" | "II" | "III";
export type FlightRule = "VFR" | "IFR";
export type VisualCondition = "VLOS" | "EVLOS" | "BVLOS";
export type MissionState =
  | "Draft" | "Planned" | "UnderReview" | "ReadyForRelease" | "Released"
  | "Active" | "Completed" | "Suspended" | "Aborted" | "PostFlightReview" | "Closed";
export type GateName = "maintenance" | "operator" | "safety" | "commander";

export interface MissionRevision {
  id: string;
  missionId: string;
  revision: number;
  profileId: "fac-state-aviation" | "private-certified" | "civil-public";
  state: MissionState;
  aircraft: readonly AircraftAssignment[];
  flightRule: FlightRule;
  visualCondition: VisualCondition;
  configuration: "unarmed-isr" | "unarmed-support" | "armed" | "strike";
  route: RouteSafetyFacts;
  crew: readonly CrewAssignment[];
  evidenceSnapshotId: string;
  policyPackageId?: string;
  dataSnapshots: readonly DataSnapshotRef[];
  riskAssessment: RiskAssessmentInput;
}

export interface RuleEvaluation {
  requirementId: string;
  result: "pass" | "fail" | "unknown" | "expired" | "not-reviewed";
  severity: "hard" | "soft" | "advisory";
  reason: string;
  evidenceRefs: readonly string[];
  affectedGates: readonly GateName[];
}

export interface SafetyBlocker {
  code: string;
  conceptId: string;
  severity: "hard" | "policy" | "data" | "authority";
  explanationKey: string;
  evidenceRefs: readonly string[];
}

export interface SafetyEvaluationResult {
  missionRevisionId: string;
  status: "ready" | "conditional" | "blocked" | "degraded";
  evaluations: readonly RuleEvaluation[];
  blockers: readonly SafetyBlocker[];
  invalidatedGates: readonly GateName[];
  kernelVersion: string;
}

export interface SafetyEvaluationInput {
  mission: MissionRevision;
  requirements: readonly NormalizedRequirement[];
  policy: PolicyPackage | undefined;
  nowUtc: string;
}

export function evaluateMission(input: SafetyEvaluationInput): SafetyEvaluationResult;
export function transitionMission(input: TransitionInput): TransitionResult;
export function invalidateForChange(input: MaterialChangeInput): InvalidationResult;
export function evaluateFourGates(input: GateEvaluationInput): FourGateResult;

export interface AircraftAssignment {
  aircraftId: string;
  aircraftClass: AircraftClass;
  configuration: MissionRevision["configuration"];
  operatorUserId?: string;
  maintenanceReleaseId?: string;
}

export interface CrewAssignment {
  userId: string;
  role: "operator" | "observer" | "maintainer" | "safety" | "commander";
  aircraftId?: string;
  qualified: boolean;
  recencyCurrent: boolean;
  dutyStatus: "available" | "restricted" | "unavailable" | "unknown";
}

export interface RouteSafetyFacts {
  areaId: string;
  routeHash: string;
  terrainStatus: "pass" | "blocked" | "unknown" | "expired";
  obstacleStatus: "pass" | "blocked" | "unknown" | "expired";
  airspaceStatus: "pass" | "blocked" | "unknown" | "expired";
  notamStatus: "pass" | "blocked" | "unknown" | "expired";
  visualConditionStatus: "pass" | "blocked" | "unknown" | "expired";
}

export interface DataSnapshotRef {
  snapshotId: string;
  kind: "aip" | "notam" | "weather" | "terrain" | "airspace" | "policy" | "regulation";
  packageId: string;
  status: "current" | "expired" | "missing" | "conflicting" | "unverified";
  capturedAtUtc: string;
}

export interface RiskAssessmentInput {
  hazardIds: readonly string[];
  probability?: number;
  severity?: number;
  residualRiskBand?: string;
  acceptanceAuthorityId?: string;
  mitigationIds: readonly string[];
  status: "draft" | "complete" | "blocked" | "accepted";
}

export interface PolicyPackage {
  packageId: string;
  version: string;
  status: "draft" | "approved" | "expired" | "revoked";
  riskMatrix?: { probabilityLevels: number; severityLevels: number; cells: readonly string[] };
  nasoThresholds?: readonly { band: string; maxDurationHours?: number }[];
  delegatedAuthorities: readonly { role: GateName; userRole: string; bands: readonly string[] }[];
  freshness: Record<DataSnapshotRef["kind"], { maxAgeMinutes: number; critical: boolean }>;
  signature: string;
}

export interface TransitionInput {
  current: MissionState;
  event: "plan" | "submit-review" | "gates-complete" | "release" | "activate" | "complete" | "suspend" | "abort" | "post-flight" | "close";
  actor: { userId: string; role: CrewAssignment["role"] };
  evaluation?: SafetyEvaluationResult;
}

export interface TransitionResult {
  state: MissionState;
  auditEvent: { type: string; actorUserId: string; occurredAtUtc: string };
}

export interface MaterialChangeInput {
  mission: MissionRevision;
  field: string;
  previous: unknown;
  next: unknown;
}

export interface InvalidationResult {
  material: boolean;
  affectedRequirementIds: readonly string[];
  invalidatedGates: readonly GateName[];
  reason: string;
}

export interface ApplicabilityResult {
  applicable: boolean;
  result: RuleEvaluation["result"];
  reason: string;
  affectedGates: readonly GateName[];
}

export interface FleetSafetyFacts {
  maintenance: readonly { aircraftId: string; status: "pass" | "blocked" | "unknown" }[];
  crew: readonly CrewAssignment[];
  energy: readonly { aircraftId: string; status: "pass" | "blocked" | "unknown"; evidenceRef: string }[];
}

export interface GateEvaluationInput {
  mission: MissionRevision;
  evaluation: SafetyEvaluationResult;
  approvals: readonly { gate: GateName; decision: "accept" | "block" | "escalate"; valid: boolean }[];
  nowUtc: string;
}

export interface FourGateResult {
  status: "ready" | "conditional" | "blocked";
  gates: readonly { gate: GateName; status: "accepted" | "blocked" | "pending" | "invalid" }[];
  blockers: readonly SafetyBlocker[];
}

export interface LocalizedExplanation {
  locale: "es" | "en";
  conceptIds: readonly string[];
  labels: readonly string[];
  translationMissing: boolean;
}
```

### Task 1: Establish kernel contracts and immutable result types

**Files:**
- Create: `SMS/packages/safety-kernel/package.json`
- Create: `SMS/packages/safety-kernel/src/types.ts`
- Create: `SMS/packages/safety-kernel/src/index.ts`
- Test: `SMS/packages/safety-kernel/test/contracts.test.ts`

**Interfaces:**
- Consumes: `NormalizedRequirement`, `EvidenceReference`, and `SignedPackageManifest` from `@fac-isr/evidence`.
- Produces: the `MissionRevision`, `RuleEvaluation`, `SafetyBlocker`, and evaluation contracts above.

- [ ] **Step 1: Write the contract tests**

```ts
it("freezes evaluation results and preserves stable IDs", () => {
  const result = makeBlockedFixtureResult();
  expect(Object.isFrozen(result)).toBe(true);
  expect(result.status).toBe("blocked");
  expect(result.kernelVersion).toMatch(/^0\./);
});

it("rejects a mission with no evidence snapshot", () => {
  expect(() => parseMissionRevision({ ...validMission, evidenceSnapshotId: "" })).toThrow();
});
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `cd SMS && npm test --workspace packages/safety-kernel -- contracts.test.ts --run`
Expected: FAIL because the package and parsers do not yet exist.

- [ ] **Step 3: Implement Zod schemas and frozen DTO constructors**

Reject local-time timestamps, empty package IDs, negative reserve values, duplicate aircraft IDs, and unknown profile/configuration strings. Do not add a permissive catch-all field that could hide a future safety input.

- [ ] **Step 4: Run tests and typecheck**

Run: `cd SMS && npm test --workspace packages/safety-kernel -- contracts.test.ts --run && npm run typecheck`
Expected: PASS with strict types and explicit parse errors.

- [ ] **Step 5: Commit**

```bash
git add SMS/packages/safety-kernel
git commit -m "feat(safety-kernel): define immutable mission contracts"
```

### Task 2: Implement applicability predicates and hard blockers

**Files:**
- Create: `SMS/packages/safety-kernel/src/applicability.ts`
- Create: `SMS/packages/safety-kernel/src/terminology.ts`
- Test: `SMS/packages/safety-kernel/test/applicability.test.ts`
- Test: `SMS/packages/safety-kernel/test/fixtures/all-classes.json`
- Test: `SMS/packages/safety-kernel/test/fixtures/blocked-cases.json`

**Interfaces:**
- `getClassBand(mtowKg): AircraftClass`
- `evaluateApplicability(mission, requirement, policy): ApplicabilityResult`
- `buildHardBlockers(mission, facts): SafetyBlocker[]`

- [ ] **Step 1: Write golden tests for all RACAE classes and blockers**

```ts
it.each([
  [0.015, "IA"], [6.999, "IA"], [7, "IB"], [14.999, "IB"],
  [15, "IC"], [149.999, "IC"], [150.001, "II"], [600, "II"], [600.001, "III"],
])("maps %s kg to class %s", (mtow, expected) => {
  expect(getClassBand(mtow)).toBe(expected);
});

it("rejects the unclassified 150 kg boundary rather than inventing a class", () => {
  expect(() => getClassBand(150)).toThrow("unclassified");
});

it.each([
  ["armed", "CONFIGURATION_OUT_OF_SCOPE"],
  ["strike", "CONFIGURATION_OUT_OF_SCOPE"],
  ["unarmed-isr", "MISSING_OPERATOR_PER_AIRCRAFT"],
  ["unarmed-isr", "SWARM_RESEARCH_NON_DISPATCHABLE"],
])("returns the required operational blocker", (configuration, code) => {
  expect(buildHardBlockers(fixtureWith(configuration), factsForMissingOperators)).toContainEqual(
    expect.objectContaining({ code }),
  );
});
```

- [ ] **Step 2: Run tests to verify missing predicates fail**

Run: `cd SMS && npm test --workspace packages/safety-kernel -- applicability.test.ts --run`
Expected: FAIL until class mapping and blockers exist.

- [ ] **Step 3: Implement exact class boundaries and profile predicates**

Use grams/ kilograms exactly as stated; reject `0`, negative, NaN, and `Infinity`. Enforce the first-profile configuration allowlist. Require one assigned qualified operator per aircraft for operational missions, and produce the persistent research-only blocker for one-to-many swarm scenarios.

- [ ] **Step 4: Add source-backed predicates for autonomous mode and flight rules**

RACAE 94 section 94.155 yields a hard block for autonomous mode and a conditional result only when supervised automation, human intervention, and the approved capability evidence are present. IFR requires an approved rule package, aircraft/equipment capability, segregated airspace facts, and authorization evidence; class alone is insufficient.

- [ ] **Step 5: Run tests, including property tests for boundary monotonicity**

Run: `cd SMS && npm test --workspace packages/safety-kernel -- applicability.test.ts --run`
Expected: PASS for every class boundary, armed/strike block, one-operator rule, autonomous rule, and IFR evidence condition.

- [ ] **Step 6: Commit**

```bash
git add SMS/packages/safety-kernel/src/applicability.ts SMS/packages/safety-kernel/src/terminology.ts SMS/packages/safety-kernel/test
git commit -m "feat(safety-kernel): enforce RACAE class and operation applicability"
```

### Task 3: Implement deterministic rule evaluation and explanations

**Files:**
- Create: `SMS/packages/safety-kernel/src/evaluate.ts`
- Modify: `SMS/packages/safety-kernel/src/index.ts`
- Test: `SMS/packages/safety-kernel/test/evaluate.test.ts`
- Test: `SMS/packages/safety-kernel/test/fixtures/golden-missions.json`

**Interfaces:**
- `evaluateMission(input): SafetyEvaluationResult`
- `explainEvaluation(evaluation, locale): LocalizedExplanation`

- [ ] **Step 1: Write tests for pass, fail, unknown, expired, and locale-equivalent outputs**

```ts
it("blocks when a hard requirement is unknown", () => {
  const result = evaluateMission({ mission: validMission, requirements: [unknownHardRule], policy: approvedPolicy, nowUtc });
  expect(result.status).toBe("blocked");
  expect(result.blockers[0].code).toBe("REQUIREMENT_UNKNOWN");
});

it("does not change behavior when the explanation locale changes", () => {
  const result = evaluateMission(validInput);
  expect(explainEvaluation(result, "es").conceptIds).toEqual(explainEvaluation(result, "en").conceptIds);
});
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `cd SMS && npm test --workspace packages/safety-kernel -- evaluate.test.ts --run`
Expected: FAIL until the evaluator and explanation renderer are present.

- [ ] **Step 3: Implement stable evaluation ordering**

Sort requirements by requirement ID, evaluate applicability before evidence freshness, then apply severity and blocker policy. Include exact source references and a reason code; never use UI text as the authoritative reason.

- [ ] **Step 4: Implement bilingual explanation lookup**

Resolve only stable concept IDs through the controlled terminology package. If an English translation is missing, return the Spanish authoritative label with `translationMissing: true`; never invent a translation at runtime.

- [ ] **Step 5: Run focused and property tests**

Run: `cd SMS && npm test --workspace packages/safety-kernel -- evaluate.test.ts --run`
Expected: PASS; fixed inputs produce byte-stable JSON results and Spanish/English output has identical decision semantics.

- [ ] **Step 6: Commit**

```bash
git add SMS/packages/safety-kernel/src/evaluate.ts SMS/packages/safety-kernel/src/index.ts SMS/packages/safety-kernel/test
git commit -m "feat(safety-kernel): evaluate traceable safety rules"
```

### Task 4: Implement mission lifecycle and material-change invalidation

**Files:**
- Create: `SMS/packages/safety-kernel/src/lifecycle.ts`
- Create: `SMS/packages/safety-kernel/src/dependencies.ts`
- Test: `SMS/packages/safety-kernel/test/lifecycle.test.ts`
- Test: `SMS/packages/safety-kernel/test/dependencies.test.ts`

**Interfaces:**
- `transitionMission({ current, event, actor }): TransitionResult`
- `invalidateForChange({ field, previous, next, dependencyGraph }): InvalidationResult`
- `createMissionRevision(mission, change): MissionRevision`

- [ ] **Step 1: Write state-transition tests**

```ts
it("does not permit UnderReview to skip the four gates", () => {
  expect(() => transitionMission({ current: "UnderReview", event: "activate", actor: commander })).toThrow("gate");
});

it("creates a new revision when the route changes", () => {
  const result = createMissionRevision(releasedMission, { field: "route", next: changedRoute });
  expect(result.revision).toBe(releasedMission.revision + 1);
  expect(result.state).toBe("Planned");
});
```

- [ ] **Step 2: Run tests to verify absent transitions fail**

Run: `cd SMS && npm test --workspace packages/safety-kernel -- lifecycle.test.ts dependencies.test.ts --run`
Expected: FAIL until transition and dependency functions exist.

- [ ] **Step 3: Implement the authoritative lifecycle**

Allow only `Draft → Planned → UnderReview → ReadyForRelease → Released → Active → Completed/PostFlightReview → Closed`, with explicit `Suspended` and `Aborted` paths. Reject activation from any state with unresolved hard blockers or unapproved gates.

- [ ] **Step 4: Implement field dependencies**

Map aircraft/GCS/payload/battery/software, crew, route/altitude/visual condition, schedule, weather/NOTAM/AIP, risk/mitigation/exception, and policy/evidence changes to the exact evaluations and gates they affect. A material change never silently carries forward an approval.

- [ ] **Step 5: Run dependency matrix tests**

Run: `cd SMS && npm test --workspace packages/safety-kernel -- lifecycle.test.ts dependencies.test.ts --run`
Expected: PASS; changing a battery invalidates energy and affected gates, while changing a non-material display note invalidates none.

- [ ] **Step 6: Commit**

```bash
git add SMS/packages/safety-kernel/src/lifecycle.ts SMS/packages/safety-kernel/src/dependencies.ts SMS/packages/safety-kernel/test
git commit -m "feat(safety-kernel): add revisioned mission lifecycle"
```

### Task 5: Implement risk, NASO, data freshness, and controlled exceptions

**Files:**
- Create: `SMS/packages/safety-kernel/src/risk.ts`
- Test: `SMS/packages/safety-kernel/test/risk.test.ts`
- Test: `SMS/packages/safety-kernel/test/freshness.test.ts`

**Interfaces:**
- `evaluateRisk(input): RiskEvaluation`
- `evaluateFreshness(snapshot, policy, nowUtc): FreshnessResult`
- `evaluateException(exception, policy, nowUtc): ExceptionResult`

- [ ] **Step 1: Write blocked and conditional risk tests**

```ts
it("blocks when the active policy has no approved probability/severity matrix", () => {
  expect(evaluateRisk({ ...riskInput, policy: undefined }).status).toBe("blocked");
});

it("requires every degraded-data exception field", () => {
  expect(evaluateException({ ...exception, alternateVerifiedSource: undefined }, policy, nowUtc).status)
    .toBe("blocked");
});
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd SMS && npm test --workspace packages/safety-kernel -- risk.test.ts freshness.test.ts --run`
Expected: FAIL until risk and freshness evaluation exists.

- [ ] **Step 3: Implement approved-matrix-only evaluation**

Consume matrix cells, NASO thresholds, residual-risk bands, and delegated authorities from a signed policy package. Do not invent default institutional acceptance levels. Return `blocked` when risk cannot be assigned or the authority is missing.

- [ ] **Step 4: Implement freshness and exceptions**

Critical data beyond its maximum age becomes `expired`. A controlled exception requires stale/missing dataset, alternate verified source, consequence, mitigation, validity end, safety review, correct risk authority, and operator acknowledgement; exceptions do not copy into a new revision.

- [ ] **Step 5: Run property tests for time boundaries and UTC**

Run: `cd SMS && npm test --workspace packages/safety-kernel -- risk.test.ts freshness.test.ts --run`
Expected: PASS at exact expiry instants, with no daylight-saving or local-time ambiguity.

- [ ] **Step 6: Commit**

```bash
git add SMS/packages/safety-kernel/src/risk.ts SMS/packages/safety-kernel/test
git commit -m "feat(safety-kernel): enforce risk and evidence freshness"
```

### Task 6: Implement the four-gate release engine and audit events

**Files:**
- Create: `SMS/packages/safety-kernel/src/gates.ts`
- Create: `SMS/packages/safety-kernel/src/audit.ts`
- Test: `SMS/packages/safety-kernel/test/gates.test.ts`
- Test: `SMS/packages/safety-kernel/test/audit.test.ts`

**Interfaces:**
- `evaluateFourGates(input): FourGateResult`
- `recordGateDecision(input): GateApprovalEvent`
- `invalidateGateApprovals(invalidation): GateApprovalEvent[]`

- [ ] **Step 1: Write role-separation and operator-authority tests**

```ts
it("requires every assigned operator acceptance", () => {
  const result = evaluateFourGates(inputWithTwoAircraftAndOneOperator);
  expect(result.blockers.map(({ code }) => code)).toContain("MISSING_OPERATOR_PER_AIRCRAFT");
});

it("does not let commander authorization override an operator no-go", () => {
  const result = evaluateFourGates(inputWithOperatorNoGoAndCommanderYes);
  expect(result.status).toBe("blocked");
});
```

- [ ] **Step 2: Run tests to verify absent gate logic fails**

Run: `cd SMS && npm test --workspace packages/safety-kernel -- gates.test.ts audit.test.ts --run`
Expected: FAIL until gate evaluation and append-only events exist.

- [ ] **Step 3: Implement maintenance, operator, safety, and commander gate predicates**

Each gate has independent role permission, identity, timestamp, evidence snapshot, policy version, decision, and reason. The commander cannot sign for maintenance or operator acceptance; safety may block/escalate but cannot replace operator responsibility.

- [ ] **Step 4: Implement append-only approval and invalidation events**

Serialize gate decisions as hash-chained events. A material change adds invalidation events and returns the mission to `Planned` or `UnderReview`; recovery cannot recreate an approval without a new signed decision.

- [ ] **Step 5: Run gate, concurrency, and hash-chain tests**

Run: `cd SMS && npm test --workspace packages/safety-kernel -- gates.test.ts audit.test.ts --run`
Expected: PASS; duplicate decisions, wrong roles, stale dependencies, and altered event hashes fail explicitly.

- [ ] **Step 6: Commit**

```bash
git add SMS/packages/safety-kernel/src/gates.ts SMS/packages/safety-kernel/src/audit.ts SMS/packages/safety-kernel/test
git commit -m "feat(safety-kernel): enforce four-gate release authority"
```

### Task 7: Assemble golden State Aviation verification fixtures

**Files:**
- Create: `SMS/packages/safety-kernel/test/fixtures/all-racae-classes.json`
- Create: `SMS/packages/safety-kernel/test/fixtures/golden-blocked-cases.json`
- Create: `SMS/packages/safety-kernel/test/golden.test.ts`
- Create: `SMS/docs/provenance/kernel-golden-case-report.md`

**Interfaces:**
- Consumes: P0 signed normalized requirements and approved policy fixture.
- Produces: reproducible proof that every first-release class and known safety failure is represented.

- [ ] **Step 1: Add golden fixtures for IA, IB, IC, II, and III**

Provide unarmed ISR and support cases, VFR/VLOS cases, and IC+ IFR cases only with explicit segregated-airspace, equipment, and authorization evidence. Include a non-dispatchable research swarm fixture.

- [ ] **Step 2: Add golden blocked cases**

Include missing operator, stale METAR, airspace conflict, insufficient reserve, expired qualification, invalid maintenance release, missing risk matrix, unsigned policy, armed configuration, autonomous mode, one-to-many operational staffing, and unacceptable residual risk.

- [ ] **Step 3: Run the golden suite**

Run: `cd SMS && npm test --workspace packages/safety-kernel -- golden.test.ts --run`
Expected: PASS; no blocked case produces `ready`, no locale changes semantics, and every result includes evidence references.

- [ ] **Step 4: Record the report and commit**

```bash
git add SMS/packages/safety-kernel/test/fixtures SMS/packages/safety-kernel/test/golden.test.ts SMS/docs/provenance/kernel-golden-case-report.md
git commit -m "test(safety-kernel): add class-complete golden safety cases"
```

## P1 Completion Evidence

P1 is complete when pure-kernel tests pass without a browser or API, all RACAE classes have fixtures, all named hard blocks remain blocked, the four roles cannot substitute for one another, material changes invalidate precisely affected approvals, and a missing approved policy package prevents operational readiness.
