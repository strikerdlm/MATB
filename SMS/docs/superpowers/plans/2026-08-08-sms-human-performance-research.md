# SMS Assurance and Human-Performance Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Human-subject research boundaries require a separate review gate from operational safety acceptance.

**Goal:** Add RACAE 219-aligned SMS assurance, operational human-performance controls, and a separately governed human-factors research laboratory for FAC ISR operations without mixing operational identities, medical data, or research participants.

**Architecture:** `@fac-isr/sms` models organizational hazards, risk, CAPA, audits, indicators, ERP, and management of change. `@fac-isr/human-performance` models privacy-minimized operational duty/workload controls. `@fac-isr/research` uses separate schemas, keys, permissions, protocol/ethics/consent records, pseudonymous participants, synchronized events, deterministic replay, and deidentified exports. Research findings can inform SMS assurance only through an approved aggregate review.

**Tech Stack:** TypeScript strict; Zod; SQLite separate operational/research databases; Vitest; fast-check; MATB adapter over explicit research-only IPC/file contract; CSV/JSON/Parquet exports; no automated diagnosis or fitness-to-fly decision.

## Global Constraints

- SMS follows RACAE 219 structure: safety policy/objectives, safety risk management, safety assurance, and safety promotion.
- Mission hazards may be promoted into the organizational hazard register; corrective actions require owner, due date, evidence, verification, effectiveness review, and closure authority.
- Operational records retain only minimum identity, qualification, duty, workload, screen-exposure, CRM, alert, and self-declared safety-status fields.
- The operational module never stores diagnosis, clinical reasoning, or automated fitness-to-fly decisions.
- Research records are physically and logically separated from operational records and use separate keys and permissions.
- Research requires protocol, ethics approval, informed consent, pseudonymous participant code, condition assignment, and deidentified export.
- Research mode and swarm research are permanently labelled non-dispatchable and cannot be cloned directly into an operational mission.
- MATB, HRV, eye tracking, and psychomotor sources are research-only adapters; they cannot alter operational qualification or release eligibility.
- Approved aggregate research findings may inform training, interface changes, or SMS assurance but cannot automatically change a person’s status.

## File Map

- Create: `SMS/packages/sms/package.json`
- Create: `SMS/packages/sms/src/types.ts`
- Create: `SMS/packages/sms/src/hazards.ts`
- Create: `SMS/packages/sms/src/capa.ts`
- Create: `SMS/packages/sms/src/audits.ts`
- Create: `SMS/packages/sms/src/indicators.ts`
- Create: `SMS/packages/sms/src/moc.ts`
- Create: `SMS/packages/sms/src/erp.ts`
- Create: `SMS/packages/sms/src/index.ts`
- Create: `SMS/packages/human-performance/package.json`
- Create: `SMS/packages/human-performance/src/types.ts`
- Create: `SMS/packages/human-performance/src/operational.ts`
- Create: `SMS/packages/human-performance/src/index.ts`
- Create: `SMS/packages/research/package.json`
- Create: `SMS/packages/research/src/types.ts`
- Create: `SMS/packages/research/src/protocol.ts`
- Create: `SMS/packages/research/src/consent.ts`
- Create: `SMS/packages/research/src/instruments.ts`
- Create: `SMS/packages/research/src/matb-adapter.ts`
- Create: `SMS/packages/research/src/replay.ts`
- Create: `SMS/packages/research/src/export.ts`
- Create: `SMS/packages/research/src/index.ts`
- Test: `SMS/packages/sms/test/*.test.ts`
- Test: `SMS/packages/human-performance/test/*.test.ts`
- Test: `SMS/packages/research/test/*.test.ts`
- Create: `SMS/docs/provenance/research-data-dictionary.md`

## Interfaces

```ts
export interface Hazard {
  id: string;
  title: string;
  source: "mission" | "occurrence" | "audit" | "research-aggregate" | "management-of-change";
  description: string;
  causes: readonly string[];
  consequences: readonly string[];
  ownerId: string;
  status: "open" | "controlled" | "accepted" | "closed";
  riskAssessmentIds: readonly string[];
}

export interface OperationalHumanPerformanceStatus {
  userId: string;
  role: string;
  dutyPeriodId: string;
  qualificationStatus: "current" | "restricted" | "expired" | "unknown";
  fatigueSelfDeclaration: "able" | "not-able" | "not-recorded";
  screenExposureMinutes: number;
  workloadLevel: "low" | "moderate" | "high" | "unknown";
  alertLoad: number;
  status: "available" | "restricted" | "unavailable" | "unknown";
  evidenceRefs: readonly string[];
}

export interface ResearchSession {
  id: string;
  protocolId: string;
  ethicsApprovalId: string;
  participantCode: string;
  conditionAssignment: string;
  startedAtUtc: string;
  endedAtUtc?: string;
  nonDispatchable: true;
  events: readonly ResearchEvent[];
}

export type ParticipantCode = string & { readonly __brand: "ParticipantCode" };

export interface ResearchEvent {
  eventId: string;
  sessionId: string;
  occurredAtUtc: string;
  sequence: number;
  type: string;
  dataDomain: "research";
  nonDispatchable: true;
  payload: Record<string, unknown>;
  quality: "valid" | "degraded" | "rejected";
}

export interface Protocol {
  id: string;
  version: string;
  title: string;
  investigatorId: string;
  ethicsApprovalId: string;
  permittedInstruments: readonly string[];
  permittedSensors: readonly string[];
  retentionDays: number;
  status: "draft" | "approved" | "expired" | "closed";
}

export interface EthicsApproval {
  id: string;
  protocolId: string;
  status: "current" | "expired" | "withdrawn";
  approvedFromUtc: string;
  expiresAtUtc: string;
}

export interface ConsentRecord {
  id: string;
  protocolId: string;
  participantCode: ParticipantCode;
  consentVersion: string;
  consentedAtUtc: string;
  withdrawnAtUtc?: string;
}

export interface ConditionAssignment {
  sessionId: string;
  conditionId: string;
  assignedAtUtc: string;
  randomizationBlock?: string;
}

export interface InstrumentDefinition {
  id: string;
  name: "SAGAT" | "NASA-TLX" | "ISA" | "Bedford" | "SART" | "custom";
  version: string;
  responseSchema: Record<string, unknown>;
  status: "approved-template" | "protocol-specific" | "retired";
}

export interface InstrumentResponse {
  sessionId: string;
  instrumentId: string;
  administeredAtUtc: string;
  values: Record<string, number | string | null>;
  missingReason?: string;
}

export interface WorkloadPulse {
  userId: string;
  missionRevisionId: string;
  observedAtUtc: string;
  level: "low" | "moderate" | "high" | "unknown";
  source: "self-report" | "task-demand" | "alert-load";
  evidenceRefs: readonly string[];
}

export interface CrmBrief {
  missionRevisionId: string;
  participants: readonly { userId: string; role: string }[];
  communicationPlan: string;
  transferOfControl: string;
  incapacitationPlan: string;
  acknowledgedBy: readonly string[];
}

export interface ResearchAdapter {
  readonly adapterId: string;
  connect(session: ResearchSession, signal: AbortSignal): Promise<void>;
  readEvent(signal: AbortSignal): Promise<ResearchEvent | null>;
  close(): Promise<void>;
}

export interface CorrectiveAction {
  id: string;
  ownerId: string;
  dueAtUtc: string;
  evidence: readonly string[];
  verification?: string;
  effectivenessReview?: string;
  closureAuthorityId?: string;
  status: "open" | "verified" | "closed";
}

export interface AuditFinding {
  id: string;
  criterion: string;
  scope: string;
  evidenceRefs: readonly string[];
  ownerId: string;
  dueAtUtc: string;
  status: "open" | "closed";
}

export interface MocCase {
  id: string;
  changeDescription: string;
  impactAnalysis?: string;
  affectedHazards: readonly string[];
  affectedRequirements: readonly string[];
  approvals: readonly string[];
  status: "open" | "approved" | "implemented" | "verified" | "closed";
}

export interface AggregateReview {
  id: string;
  protocolIds: readonly string[];
  minimumCellSize: number;
  permittedUses: readonly ("training" | "interface-change" | "sms-assurance")[];
  findings: readonly string[];
  limitations: readonly string[];
  reviewerId: string;
}

export interface Occurrence {
  id: string;
  missionRevisionId: string;
  reportedAtUtc: string;
  classification: "incident" | "accident" | "hazard-report" | "equipment-damage" | "near-miss";
  description: string;
  reportingDeadlineUtc?: string;
  status: "open" | "under-review" | "reported" | "closed";
  evidenceRefs: readonly string[];
}

export interface PromotionResult {
  hazard: Hazard;
  sourceMissionId: string;
  promotedAtUtc: string;
}

export interface VerificationResult {
  status: "verified" | "ineffective" | "blocked";
  evidenceRefs: readonly string[];
  reviewerId?: string;
}

export interface ErpReadiness {
  status: "ready" | "blocked" | "expired" | "unknown";
  missing: readonly string[];
  nextReviewAtUtc?: string;
}

export interface SpiStatus {
  level: "normal" | "alert" | "action" | "unknown";
  reason: string;
  dataQuality: "complete" | "incomplete" | "stale";
}

export interface AlertLoadResult {
  level: "low" | "moderate" | "high" | "unknown";
  count: number;
  unresolved: number;
  escalationRequired: boolean;
  evidenceRefs: readonly string[];
}
```

### Task 1: Define SMS, operational human-performance, and research schemas

**Files:**
- Create: `SMS/packages/sms/package.json`
- Create: `SMS/packages/sms/src/types.ts`
- Create: `SMS/packages/human-performance/package.json`
- Create: `SMS/packages/human-performance/src/types.ts`
- Create: `SMS/packages/research/package.json`
- Create: `SMS/packages/research/src/types.ts`
- Test: `SMS/packages/sms/test/contracts.test.ts`
- Test: `SMS/packages/human-performance/test/contracts.test.ts`
- Test: `SMS/packages/research/test/contracts.test.ts`

**Interfaces:**
- Produces the interfaces above and explicit separation markers consumed by P4 and later UI work.

- [ ] **Step 1: Write schema and cross-boundary tests**

```ts
it("requires ethics approval and consent before a research session", () => {
  expect(() => parseResearchSession({ ...validSession, ethicsApprovalId: "" })).toThrow();
});

it("does not accept operational user IDs in a research event", () => {
  expect(() => parseResearchEvent({ ...validEvent, operationalUserId: "U-1" })).toThrow("separation");
});
```

- [ ] **Step 2: Run tests to verify absent schemas fail**

Run: `cd SMS && npm test --workspaces -- contracts.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement strict schemas and separate branded IDs**

Use separate `OperationalUserId` and `ParticipantCode` brands, distinct database connection factories, and no shared table containing both. The research session has a literal `nonDispatchable: true` field so it cannot be omitted by a caller.

- [ ] **Step 4: Run tests and commit**

Run: `cd SMS && npm test --workspaces -- contracts.test.ts --run && npm run typecheck`
Expected: PASS.

```bash
git add SMS/packages/sms SMS/packages/human-performance SMS/packages/research
git commit -m "feat(hf): define isolated SMS and research contracts"
```

### Task 2: Implement hazard, risk, occurrence, CAPA, and ERP workflows

**Files:**
- Create: `SMS/packages/sms/src/hazards.ts`
- Create: `SMS/packages/sms/src/capa.ts`
- Create: `SMS/packages/sms/src/erp.ts`
- Test: `SMS/packages/sms/test/hazards.test.ts`
- Test: `SMS/packages/sms/test/capa.test.ts`
- Test: `SMS/packages/sms/test/erp.test.ts`

**Interfaces:**
- `createHazard(input): Hazard`
- `promoteMissionHazard(input): PromotionResult`
- `createCorrectiveAction(input): CorrectiveAction`
- `verifyCorrectiveAction(input): VerificationResult`
- `evaluateErpReadiness(input): ErpReadiness`

- [ ] **Step 1: Write workflow tests**

```ts
it("requires evidence and effectiveness review before CAPA closure", () => {
  expect(closeCorrectiveAction({ ...capa, evidence: [], effectivenessReview: undefined })).toThrow("closure");
});

it("promotes a mission hazard with its source and residual risk", () => {
  const result = promoteMissionHazard({ missionHazard, organizationalOwnerId: "SMS-1" });
  expect(result.hazard.source).toBe("mission");
  expect(result.hazard.riskAssessmentIds).toContain(missionHazard.residualRiskId);
});
```

- [ ] **Step 2: Run tests to verify missing workflow fails**

Run: `cd SMS && npm test --workspace packages/sms -- hazards.test.ts capa.test.ts erp.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement RACAE 219-aligned records**

Support accountable executive, roles/delegated risk authorities, hazard register, mission/systemic risk, occurrence intake/reporting deadlines, CAPA, ERP ownership/exercises/review dates, training/safety promotion, and evidence-linked closure. Do not invent institutional risk thresholds; consume P1 policy facts.

- [ ] **Step 4: Implement ERP readiness and exercise records**

Require emergency plan owner, current contact/coordination facts, aircraft/crew/route contingencies, exercise date, findings, corrective actions, and next review. An ERP check may block a mission when policy says it is required and the plan is missing or expired.

- [ ] **Step 5: Run tests and commit**

Run: `cd SMS && npm test --workspace packages/sms -- hazards.test.ts capa.test.ts erp.test.ts --run`
Expected: PASS.

```bash
git add SMS/packages/sms/src/hazards.ts SMS/packages/sms/src/capa.ts SMS/packages/sms/src/erp.ts SMS/packages/sms/test
git commit -m "feat(sms): add hazard CAPA and ERP assurance workflows"
```

### Task 3: Implement audits, safety performance indicators, and management of change

**Files:**
- Create: `SMS/packages/sms/src/audits.ts`
- Create: `SMS/packages/sms/src/indicators.ts`
- Create: `SMS/packages/sms/src/moc.ts`
- Test: `SMS/packages/sms/test/audits.test.ts`
- Test: `SMS/packages/sms/test/indicators.test.ts`
- Test: `SMS/packages/sms/test/moc.test.ts`

**Interfaces:**
- `createAuditFinding(input): AuditFinding`
- `evaluateSpi(value, threshold): SpiStatus`
- `openManagementOfChange(input): MocCase`
- `completeMoc(case, evidence): MocCase`

- [ ] **Step 1: Write audit/SPI/MOC tests**

```ts
it("does not close an MOC without impact analysis and verification", () => {
  expect(() => completeMoc({ ...openCase, impactAnalysis: undefined }, [])).toThrow("impact");
});

it("raises an SPI alert at the configured policy threshold", () => {
  expect(evaluateSpi({ value: 4, unit: "events/100-flight-hours" }, { alertAt: 3, actionAt: 5 }).level)
    .toBe("alert");
});
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd SMS && npm test --workspace packages/sms -- audits.test.ts indicators.test.ts moc.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement evidence-linked audit and indicator records**

Audit findings include scope, criterion, evidence, owner, due date, risk, corrective action, verification, and closure authority. SPI definitions include numerator/denominator, window, threshold policy ID, data-quality state, and version; do not calculate a meaningful indicator from missing data.

- [ ] **Step 4: Implement MOC impact and approval flow**

Changes to aircraft/software/policy/regulation/crew/workflow/map packages create MOC cases with affected hazards, requirements, training, documents, interfaces, and approval roles. A completed MOC produces a package/version impact record; it cannot silently mutate an active mission snapshot.

- [ ] **Step 5: Run tests and commit**

Run: `cd SMS && npm test --workspace packages/sms -- audits.test.ts indicators.test.ts moc.test.ts --run`
Expected: PASS.

```bash
git add SMS/packages/sms/src/audits.ts SMS/packages/sms/src/indicators.ts SMS/packages/sms/src/moc.ts SMS/packages/sms/test
git commit -m "feat(sms): add assurance indicators and change control"
```

### Task 4: Implement privacy-minimized operational human-performance controls

**Files:**
- Create: `SMS/packages/human-performance/src/operational.ts`
- Create: `SMS/packages/human-performance/src/terminology.ts`
- Test: `SMS/packages/human-performance/test/operational.test.ts`
- Test: `SMS/packages/human-performance/test/privacy.test.ts`

**Interfaces:**
- `evaluateOperationalStatus(input): OperationalHumanPerformanceStatus`
- `recordWorkloadPulse(input): WorkloadPulse`
- `evaluateAlertLoad(events, policy): AlertLoadResult`
- `createCrmBrief(input): CrmBrief`

- [ ] **Step 1: Write duty, fatigue, screen, alert, and privacy tests**

```ts
it("blocks when screen exposure exceeds the approved policy limit", () => {
  expect(evaluateOperationalStatus({ ...validStatusInput, screenExposureMinutes: 999 }).status)
    .toBe("restricted");
});

it("stores no diagnosis or clinical reasoning", () => {
  const result = evaluateOperationalStatus(validStatusInput);
  expect(Object.keys(result)).not.toContain("diagnosis");
  expect(JSON.stringify(result)).not.toMatch(/clinical|medical reasoning|fit-to-fly/i);
});
```

- [ ] **Step 2: Run tests to verify absent operational controls fail**

Run: `cd SMS && npm test --workspace packages/human-performance -- operational.test.ts privacy.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement role/recency/duty/workload controls**

Consume approved policy limits for duty/rest, cumulative workload, screen exposure, alert load, automation-mode awareness, transfer-of-control, incapacitation readiness, CRM, and self-declared able/not-able status. Return minimum status and evidence only; never produce a medical determination.

- [ ] **Step 4: Implement alarm-flood and escalation detection**

Count alerts by phase, severity, acknowledgment latency, duplicate rate, and unresolved status. Return workload/alert findings with source policy and recommended human action; never issue aircraft commands.

- [ ] **Step 5: Run tests and commit**

Run: `cd SMS && npm test --workspace packages/human-performance -- operational.test.ts privacy.test.ts --run`
Expected: PASS.

```bash
git add SMS/packages/human-performance/src SMS/packages/human-performance/test
git commit -m "feat(hf): add privacy-minimized operational controls"
```

### Task 5: Implement research protocol, consent, participant coding, and instruments

**Files:**
- Create: `SMS/packages/research/src/protocol.ts`
- Create: `SMS/packages/research/src/consent.ts`
- Create: `SMS/packages/research/src/instruments.ts`
- Test: `SMS/packages/research/test/protocol.test.ts`
- Test: `SMS/packages/research/test/consent.test.ts`
- Test: `SMS/packages/research/test/instruments.test.ts`
- Create: `SMS/docs/provenance/research-data-dictionary.md`

**Interfaces:**
- `registerProtocol(input): Protocol`
- `openConsentedSession(input): ResearchSession`
- `assignCondition(sessionId, condition): ConditionAssignment`
- `recordInstrumentResponse(input): InstrumentResponse`

- [ ] **Step 1: Write ethics/consent/instrument tests**

```ts
it("cannot open a session without current ethics approval and consent", () => {
  expect(() => openConsentedSession({ ...validSessionInput, consent: undefined })).toThrow("consent");
});

it.each(["SAGAT", "NASA-TLX", "ISA", "Bedford", "SART"])("registers the controlled %s instrument", (name) => {
  expect(getInstrument(name).status).toBe("approved-template");
});
```

- [ ] **Step 2: Run tests to verify missing research workflow fails**

Run: `cd SMS && npm test --workspace packages/research -- protocol.test.ts consent.test.ts instruments.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement protocol and consent gates**

Require protocol version, investigator, ethics approval ID/status/expiry, consent version and UTC timestamp, participant code, data-minimization statement, retention, withdrawal behavior, and permitted sensors. Store no operational user ID in session rows.

- [ ] **Step 4: Register validated instruments and custom schemas**

Represent SAGAT, NASA-TLX, ISA, Bedford workload, SART, controlled custom instruments, and synchronized mission/research event definitions. Validate response ranges, missingness, administration timing, and instrument version.

- [ ] **Step 5: Run tests and commit**

Run: `cd SMS && npm test --workspace packages/research -- protocol.test.ts consent.test.ts instruments.test.ts --run`
Expected: PASS.

```bash
git add SMS/packages/research/src SMS/packages/research/test SMS/docs/provenance/research-data-dictionary.md
git commit -m "feat(research): add protocol consent and instruments"
```

### Task 6: Implement MATB and optional sensor adapters as research-only inputs

**Files:**
- Create: `SMS/packages/research/src/matb-adapter.ts`
- Create: `SMS/packages/research/src/sensor-adapters.ts`
- Test: `SMS/packages/research/test/matb-adapter.test.ts`
- Test: `SMS/packages/research/test/sensor-adapters.test.ts`

**Interfaces:**
- `ResearchAdapter.connect(session, signal): Promise<void>`
- `ResearchAdapter.readEvent(signal): Promise<ResearchEvent | null>`
- `ResearchAdapter.close(): Promise<void>`

- [ ] **Step 1: Write isolation and deterministic event tests**

```ts
it("marks MATB events as research-only", async () => {
  const event = await adapter.readEvent(abortSignal);
  expect(event?.dataDomain).toBe("research");
  expect(event?.nonDispatchable).toBe(true);
});

it("cannot write to operational qualification or mission release stores", () => {
  expect(Object.keys(adapter)).not.toContain("updateQualification");
  expect(Object.keys(adapter)).not.toContain("approveMission");
});
```

- [ ] **Step 2: Run tests to verify adapter absence fails**

Run: `cd SMS && npm test --workspace packages/research -- matb-adapter.test.ts sensor-adapters.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement explicit research IPC/file adapters**

Consume the existing MATB integration through a versioned, local, research-only event contract. Optional HRV, eye-tracking, and psychomotor adapters normalize timestamps, device metadata, quality flags, and consent scope. Reject data outside the approved protocol or with an unknown participant/session.

- [ ] **Step 4: Run tests and commit**

Run: `cd SMS && npm test --workspace packages/research -- matb-adapter.test.ts sensor-adapters.test.ts --run`
Expected: PASS; adapters cannot access operational repositories.

```bash
git add SMS/packages/research/src/matb-adapter.ts SMS/packages/research/src/sensor-adapters.ts SMS/packages/research/test
git commit -m "feat(research): add isolated MATB and sensor adapters"
```

### Task 7: Implement deterministic replay, deidentified exports, and aggregate review

**Files:**
- Create: `SMS/packages/research/src/replay.ts`
- Create: `SMS/packages/research/src/export.ts`
- Create: `SMS/packages/research/src/aggregate.ts`
- Test: `SMS/packages/research/test/replay.test.ts`
- Test: `SMS/packages/research/test/export.test.ts`
- Test: `SMS/packages/research/test/boundary.test.ts`

**Interfaces:**
- `replaySession(sessionPackage): AsyncIterable<ResearchEvent>`
- `exportDeidentified(session, format): Uint8Array | string`
- `createAggregateReview(input): AggregateReview`

- [ ] **Step 1: Write replay, redaction, and boundary tests**

```ts
it("replays the same event ordering and timing for a fixed package", async () => {
  expect(await collect(replaySession(sessionPackage))).toEqual(await collect(replaySession(sessionPackage)));
});

it("exports only participant codes and approved research variables", async () => {
  const exported = JSON.stringify(await exportDeidentified(session, "json"));
  expect(exported).not.toMatch(/name|operationalUserId|diagnosis|missionRelease/i);
});
```

- [ ] **Step 2: Run tests to verify absent replay/export fails**

Run: `cd SMS && npm test --workspace packages/research -- replay.test.ts export.test.ts boundary.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement deterministic replay and deidentified CSV/JSON/Parquet exports**

Replay uses event IDs, UTC timestamps, sequence ordering, and schema versions. Exports include protocol/ethics/consent versions, participant code, condition, instrument metadata, events, quality flags, and hashes, but exclude operational identity and classified content.

- [ ] **Step 4: Implement approved aggregate review path**

Aggregate reviews include analysis scope, minimum cell size/privacy rule, protocol and ethics references, reviewer, findings, limitations, and permitted downstream uses. The output may be linked to an SMS hazard/training/interface MOC but cannot write to operational qualification or release eligibility.

- [ ] **Step 5: Run full research boundary tests and commit**

Run: `cd SMS && npm test --workspace packages/research -- --run && npm run typecheck`
Expected: PASS; cross-database and cross-API attempts are denied and audited.

```bash
git add SMS/packages/research/src SMS/packages/research/test
git commit -m "feat(research): add replay and deidentified evidence exports"
```

### Task 8: Add SMS and research workflows to the tactical console

**Files:**
- Create: `SMS/apps/console/src/components/HumanPerformancePanel.tsx`
- Create: `SMS/apps/console/src/components/SmsDashboard.tsx`
- Create: `SMS/apps/console/src/components/ResearchProtocolPanel.tsx`
- Create: `SMS/apps/console/src/components/ResearchSessionPanel.tsx`
- Create: `SMS/apps/console/src/components/PrivacyBanner.tsx`
- Test: `SMS/apps/console/test/HumanPerformancePanel.test.tsx`
- Test: `SMS/apps/console/test/SmsDashboard.test.tsx`
- Test: `SMS/apps/console/test/ResearchBoundary.test.tsx`

**Interfaces:**
- `HumanPerformancePanel` displays minimum operational status and escalation, not medical detail.
- `SmsDashboard` displays hazards, CAPA, audits, SPI, ERP, and MOC state.
- `ResearchProtocolPanel` and `ResearchSessionPanel` are role/ethics/consent gated and show `NON-DISPATCHABLE RESEARCH` persistently.

- [ ] **Step 1: Write UI boundary tests**

```tsx
it("does not render a medical diagnosis or fitness-to-fly control", () => {
  render(<HumanPerformancePanel {...fixtureProps} />);
  expect(screen.queryByText(/diagnosis|fitness.to.fly|medical clearance/i)).toBeNull();
});

it("keeps research identity controls unavailable in the operational route", () => {
  render(<AppShell initialPath="/missions/1/monitor" />);
  expect(screen.queryByRole("button", { name: /participant identity/i })).toBeNull();
});
```

- [ ] **Step 2: Run tests to verify missing panels fail**

Run: `cd SMS && npm test --workspace apps/console -- HumanPerformancePanel.test.tsx SmsDashboard.test.tsx ResearchBoundary.test.tsx --run`
Expected: FAIL.

- [ ] **Step 3: Implement operational and SMS panels**

Show qualification/recency, duty/rest, fatigue self-declaration, screen exposure, workload, CRM, alert load, hazards, residual risk, CAPA owners/dates, SPI status, ERP review, and MOC status with source/policy references and no clinical fields.

- [ ] **Step 4: Implement gated research panels**

Show protocol/ethics/consent state, participant code, condition, instrument progress, synchronized research timeline, and export actions only to authorized researchers. Persistent labels state research-only/non-dispatchable.

- [ ] **Step 5: Run UI tests and commit**

Run: `cd SMS && npm test --workspace apps/console -- HumanPerformancePanel.test.tsx SmsDashboard.test.tsx ResearchBoundary.test.tsx --run`
Expected: PASS; UI cannot create a mission release from a research session.

```bash
git add SMS/apps/console/src/components SMS/apps/console/test
git commit -m "feat(console): add SMS and human-performance workspaces"
```

## P5 Completion Evidence

P5 is complete when SMS assurance workflows are evidence-linked and auditable, operational human-performance controls are privacy-minimized, research sessions require protocol/ethics/consent, MATB and optional sensor adapters are isolated, replay/export are deterministic and deidentified, and the console prevents research data from changing operational release or qualification.
