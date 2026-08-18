# Edge Service, Tactical Console, and Read-Only Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Use the frontend-design guidance for intentional, aviation-compatible visual design; verify every operational behavior with offline and no-C2 tests.

**Goal:** Build the deployable headless edge node and map-first bilingual workstation that persists missions locally, enforces roles and audit, presents the four-gate workflow, renders offline geospatial packages, and monitors approved read-only telemetry without a command path.

**Architecture:** A Fastify edge API serves a local React/Vite console and stores operational data in SQLite. Pure P1/P2/P3 packages remain authoritative for safety calculations. The telemetry gateway accepts only canonical status events from one-way or simulated adapters. The UI is a disciplined aviation day/night chart interface centered on the persistent Mission Safety Strip, not a weapon-system or sci-fi aesthetic.

**Tech Stack:** Node.js 22 LTS; Fastify; SQLite + Drizzle ORM; Zod; React 19 + Vite; MapLibre GL JS; PMTiles; Zustand; `@tanstack/react-query`; Vitest; React Testing Library; Playwright; axe-core; `@fac-isr/safety-kernel`; `@fac-isr/fleet`; `@fac-isr/energy`; `@fac-isr/geo`.

## Global Constraints

- Deploy on a rugged laptop/compact server and isolated LAN; standalone laptop mode must remain supported.
- The edge node must work without internet for authentication, planning, evaluation, gate review, monitoring, debrief, and export.
- Local clients use authenticated TLS; local identity storage is least-privilege and role-scoped.
- Operational data is unclassified controlled safety metadata only; the UI displays a persistent content/classification warning.
- No telemetry adapter, API route, UI action, event name, or database table may represent aircraft/GCS command, arm, launch, redirect, payload control, or recovery control.
- All four gates have separate permissions; no bulk “check all” control exists; each checklist response records accountable identity and UTC timestamp.
- The interface supports Spanish and controlled English with unchanged rule behavior, units, identifiers, and source citations.
- Day/night modes use `#081B25`, `#E6EEF0`, `#44B8C7`, `#4FA878`, `#F2AA3C`, and `#D64E4B`; status is never communicated by color alone.
- Typography uses locally stored Archivo Narrow, Atkinson Hyperlegible, and IBM Plex Mono with license records.
- Map display is dominant during planning/monitoring; tablets support briefing, checklists, review, and approvals.
- Applicable flight telemetry is preserved for at least the current RACAE minimum (RACAE 94 section 94.705) and the longer of any approved FAC retention schedule; retention decisions are versioned and auditable.

## File Map

- Create: `SMS/apps/edge-api/package.json`
- Create: `SMS/apps/edge-api/src/server.ts` — headless Fastify bootstrap and safe shutdown.
- Create: `SMS/apps/edge-api/src/config.ts` — validated local deployment configuration.
- Create: `SMS/apps/edge-api/src/db/schema.ts` — operational SQLite schema.
- Create: `SMS/apps/edge-api/src/db/migrate.ts` — migration runner and schema version.
- Create: `SMS/apps/edge-api/src/auth/*.ts` — local identities, sessions, roles, TLS, and lockout.
- Create: `SMS/apps/edge-api/src/audit/*.ts` — hash-chained append-only operational ledger.
- Create: `SMS/apps/edge-api/src/routes/missions.ts` — mission/revision APIs.
- Create: `SMS/apps/edge-api/src/routes/gates.ts` — four-gate APIs.
- Create: `SMS/apps/edge-api/src/routes/debrief.ts` — recovery, battery, discrepancy, occurrence, and debrief APIs.
- Create: `SMS/apps/edge-api/src/routes/occurrences.ts` — occurrence intake and reporting deadlines.
- Create: `SMS/apps/edge-api/src/services/postflight-service.ts` — post-flight closure and telemetry-preservation workflow.
- Create: `SMS/apps/edge-api/src/routes/telemetry.ts` — read-only status subscriptions/replay.
- Create: `SMS/apps/edge-api/src/routes/packages.ts` — signed package import/quarantine.
- Create: `SMS/apps/edge-api/src/routes/exports.ts` — signed mission export/import review.
- Create: `SMS/apps/edge-api/src/index.ts`
- Create: `SMS/apps/console/package.json`
- Create: `SMS/apps/console/src/main.tsx`
- Create: `SMS/apps/console/src/app/AppShell.tsx`
- Create: `SMS/apps/console/src/app/routes.tsx`
- Create: `SMS/apps/console/src/styles/tokens.css`
- Create: `SMS/apps/console/src/styles/operational.css`
- Create: `SMS/apps/console/src/components/MissionSafetyStrip.tsx`
- Create: `SMS/apps/console/src/components/GateStatus.tsx`
- Create: `SMS/apps/console/src/components/ChecklistPanel.tsx`
- Create: `SMS/apps/console/src/components/MapWorkspace.tsx`
- Create: `SMS/apps/console/src/components/TelemetryPanel.tsx`
- Create: `SMS/apps/console/src/components/AlertTimeline.tsx`
- Create: `SMS/apps/console/src/i18n/registry.ts`
- Create: `SMS/packages/telemetry/package.json`
- Create: `SMS/packages/telemetry/src/types.ts`
- Create: `SMS/packages/telemetry/src/gateway.ts`
- Create: `SMS/packages/telemetry/src/replay.ts`
- Test: `SMS/apps/edge-api/test/*.test.ts`
- Test: `SMS/apps/console/test/*.test.tsx`
- Test: `SMS/packages/telemetry/test/*.test.ts`
- Test: `SMS/apps/console/e2e/*.spec.ts`

## Interfaces

```ts
export interface ReadOnlyTelemetryAdapter {
  readonly adapterId: string;
  readonly aircraftId: string;
  connect(signal: AbortSignal): Promise<void>;
  readStatus(signal: AbortSignal): Promise<CanonicalTelemetry | null>;
  subscribe(listener: (event: CanonicalTelemetry) => void, signal: AbortSignal): Promise<void>;
  close(): Promise<void>;
}

export interface CanonicalTelemetry {
  eventId: string;
  aircraftId: string;
  observedAtUtc: string;
  position?: { lat: number; lon: number; altitudeMslM?: number; heightAglM?: number };
  motion?: { headingDeg?: number; groundSpeedKt?: number; verticalRateFpm?: number };
  energy?: { stateOfChargePercent?: number; voltageV?: number; currentA?: number; temperatureC?: number; reserveAtRecoveryPercent?: number };
  platform?: { propulsion?: "normal" | "degraded" | "unknown"; gnss?: "normal" | "degraded" | "unknown"; c2Link?: "normal" | "degraded" | "lost" };
  route?: { legId?: string; crossTrackM?: number; approvedArea?: boolean };
  sourcePackageIds: readonly string[];
}

export interface GateDecisionRequest {
  missionRevisionId: string;
  gate: "maintenance" | "operator" | "safety" | "commander";
  decision: "accept" | "block" | "escalate";
  reason: string;
  checklistResponseIds: readonly string[];
  evidenceSnapshotId: string;
  expectedRevision: number;
}

export interface Session {
  sessionId: string;
  userId: string;
  roles: readonly string[];
  issuedAtUtc: string;
  expiresAtUtc: string;
  lockedAtUtc?: string;
}

export interface AuthorizationResult {
  allowed: boolean;
  reason: string;
  requiredRole?: string;
}

export interface AuditEvent {
  sequence: number;
  eventId: string;
  type: string;
  actorUserId: string;
  missionRevisionId?: string;
  occurredAtUtc: string;
  payload: Record<string, unknown>;
  previousHash: string;
  hash: string;
}

export interface AuditVerificationReport {
  ok: boolean;
  firstBrokenSequence?: number;
  checkedEvents: number;
}
```

### Task 1: Scaffold the headless edge API and local database

**Files:**
- Create: `SMS/apps/edge-api/package.json`
- Create: `SMS/apps/edge-api/src/config.ts`
- Create: `SMS/apps/edge-api/src/db/schema.ts`
- Create: `SMS/apps/edge-api/src/db/migrate.ts`
- Create: `SMS/apps/edge-api/src/server.ts`
- Create: `SMS/apps/edge-api/src/index.ts`
- Test: `SMS/apps/edge-api/test/server.test.ts`
- Test: `SMS/apps/edge-api/test/schema.test.ts`

**Interfaces:**
- Produces a local Fastify server with `GET /healthz`, `GET /readyz`, and no external-network dependency.

- [ ] **Step 1: Write offline boot tests**

```ts
it("boots with internet disabled", async () => {
  const app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });
  await expect(app.inject({ method: "GET", url: "/healthz" })).resolves.toMatchObject({ statusCode: 200 });
});

it("does not claim ready before migrations and policy package validation", async () => {
  const app = await buildServer({ databaseUrl: ":memory:", internet: "disabled" });
  expect((await app.inject({ method: "GET", url: "/readyz" })).statusCode).toBe(503);
});
```

- [ ] **Step 2: Run tests to verify absent server fails**

Run: `cd SMS && npm test --workspace apps/edge-api -- server.test.ts schema.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement config validation, migrations, and Fastify bootstrap**

Validate bind address, TLS paths, database path, package directory, lock timeout, and `internet=disabled`. Use SQLite WAL mode, foreign keys, explicit schema version, and migration checks. `readyz` remains 503 until migrations, signing keys, terminology, and an active policy package are validated.

- [ ] **Step 4: Run tests and commit**

Run: `cd SMS && npm test --workspace apps/edge-api -- server.test.ts schema.test.ts --run && npm run typecheck`
Expected: PASS; no test starts a network client.

```bash
git add SMS/apps/edge-api
git commit -m "feat(edge): scaffold offline headless service"
```

### Task 2: Implement local identity, role separation, TLS, and session locking

**Files:**
- Create: `SMS/apps/edge-api/src/auth/identity.ts`
- Create: `SMS/apps/edge-api/src/auth/roles.ts`
- Create: `SMS/apps/edge-api/src/auth/session.ts`
- Create: `SMS/apps/edge-api/src/auth/tls.ts`
- Test: `SMS/apps/edge-api/test/auth.test.ts`

**Interfaces:**
- `authenticateLocal(credentials): Promise<Session>`
- `authorize(session, action): AuthorizationResult`
- `lockSession(sessionId, reason): void`

- [ ] **Step 1: Write authorization and lockout tests**

```ts
it("does not let a commander sign the maintenance gate", () => {
  expect(authorize(commanderSession, { action: "gate:maintenance:accept" }).allowed).toBe(false);
});

it("locks the session after the configured idle period", () => {
  const session = sessionAtIdleLimit;
  expect(isSessionLocked(session, nowUtc)).toBe(true);
});
```

- [ ] **Step 2: Run tests to verify missing auth fails**

Run: `cd SMS && npm test --workspace apps/edge-api -- auth.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement local role-based permissions**

Roles include commander, safety officer, maintainer, operator/remote pilot, observer, reviewer, researcher, and administrator. Gate actions require the corresponding role and mission assignment. Store minimum identity/qualification facts; protect session tokens with secure cookies or equivalent local mechanism; enforce lockout and re-authentication for signing.

- [ ] **Step 4: Implement TLS and local-network restrictions**

Require configured certificate/key paths in tactical mode, reject plaintext client access except a loopback bootstrap, and audit certificate identity. Do not add cloud auth, external identity, or internet fallback.

- [ ] **Step 5: Run tests and commit**

Run: `cd SMS && npm test --workspace apps/edge-api -- auth.test.ts --run`
Expected: PASS for least privilege, gate separation, lock, re-authentication, and failed-login audit.

```bash
git add SMS/apps/edge-api/src/auth SMS/apps/edge-api/test/auth.test.ts
git commit -m "feat(edge): enforce local role and session security"
```

### Task 3: Implement the immutable operational audit ledger

**Files:**
- Create: `SMS/apps/edge-api/src/audit/ledger.ts`
- Create: `SMS/apps/edge-api/src/audit/events.ts`
- Test: `SMS/apps/edge-api/test/audit.test.ts`

**Interfaces:**
- `appendAuditEvent(event): Promise<AuditEvent>`
- `verifyAuditChain(): Promise<AuditVerificationReport>`
- `queryAudit(filter): Promise<AuditEvent[]>`

- [ ] **Step 1: Write hash-chain and failure-mode tests**

```ts
it("detects a changed prior decision", async () => {
  await ledger.append(gateAcceptedEvent);
  await ledger.tamperForFixture(0, { reason: "changed" });
  expect((await ledger.verifyAuditChain()).ok).toBe(false);
});

it("disables approval writes when the database cannot append", async () => {
  await ledger.simulateWriteFailure();
  expect(await ledger.canApprove()).toBe(false);
});
```

- [ ] **Step 2: Run tests to verify absent ledger fails**

Run: `cd SMS && npm test --workspace apps/edge-api -- audit.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement append-only, hash-chained event persistence**

Hash canonical event JSON plus previous hash; include actor, UTC time, mission/revision, action, reason, evidence snapshot, client/session, and schema version. Only append is permitted; database write failure changes the service to read-only safe mode and disables all gate writes.

- [ ] **Step 4: Run tests and commit**

Run: `cd SMS && npm test --workspace apps/edge-api -- audit.test.ts --run`
Expected: PASS; export and verification identify the first broken event.

```bash
git add SMS/apps/edge-api/src/audit SMS/apps/edge-api/test/audit.test.ts
git commit -m "feat(edge): add append-only operational audit ledger"
```

### Task 4: Implement mission, revision, checklist, and gate APIs

**Files:**
- Create: `SMS/apps/edge-api/src/routes/missions.ts`
- Create: `SMS/apps/edge-api/src/routes/checklists.ts`
- Create: `SMS/apps/edge-api/src/routes/gates.ts`
- Create: `SMS/apps/edge-api/src/services/mission-service.ts`
- Test: `SMS/apps/edge-api/test/missions.test.ts`
- Test: `SMS/apps/edge-api/test/gates.test.ts`
- Test: `SMS/apps/edge-api/test/postflight.test.ts`

**Interfaces:**
- `POST /api/missions`
- `GET /api/missions/:missionId`
- `POST /api/missions/:missionId/revisions`
- `POST /api/revisions/:revisionId/checklist-responses`
- `POST /api/revisions/:revisionId/gates/:gate`
- `GET /api/revisions/:revisionId/safety-result`
- `POST /api/revisions/:revisionId/postflight`
- `POST /api/revisions/:revisionId/occurrences`

- [ ] **Step 1: Write route and workflow tests**

```ts
it("requires accountable checklist responses and refuses bulk completion", async () => {
  const response = await app.inject({ method: "POST", url: `/api/revisions/${id}/checklist-responses`, payload: { checkAll: true } });
  expect(response.statusCode).toBe(400);
});

it("rejects commander authorization when an operator gate is no-go", async () => {
  await acceptGate("operator", { decision: "block" });
  const response = await acceptGate("commander", { decision: "accept" });
  expect(response.statusCode).toBe(409);
});
```

- [ ] **Step 2: Run tests to verify routes fail**

Run: `cd SMS && npm test --workspace apps/edge-api -- missions.test.ts gates.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement revisioned mission routes around the pure kernel**

Validate request schemas with Zod, load signed evidence/policy snapshots, call P1/P2/P3 evaluators, persist immutable revision snapshots, and return blockers with source references. Any material change creates a revision and invalidates affected approvals; API clients cannot set `ReadyForRelease` directly.

- [ ] **Step 4: Implement explicit per-item checklists and four-gate signing**

Each item requires a response, accountable user, UTC timestamp, evidence reference where required, and optional reason. Gate signing checks role, assignment, expected revision, current kernel result, data freshness, and dependency validity. Write an audit event for every accept, block, escalate, rejection, and invalidation.

- [ ] **Step 5: Run route and concurrency tests and commit**

Run: `cd SMS && npm test --workspace apps/edge-api -- missions.test.ts gates.test.ts --run`
Expected: PASS for duplicate writes, stale revision conflicts, role separation, no bulk completion, and safe failure.

- [ ] **Step 6: Implement the post-flight workflow and run its tests**

Record aircraft recovery/shutdown/inventory, battery temperature/damage/quarantine/cycle/storage actions, discrepancies and return-to-service status, telemetry checksum/preservation/review state, occurrence screening/reporting deadline, structured crew debrief, lessons learned, hazard/CAPA links, and research instruments only when an approved protocol is present. The mission cannot close while required post-flight evidence is missing.

Run: `cd SMS && npm test --workspace apps/edge-api -- postflight.test.ts --run`
Expected: PASS; telemetry retention, occurrence deadlines, and debrief links are immutable and audited.

```bash
git add SMS/apps/edge-api/src/routes SMS/apps/edge-api/src/services SMS/apps/edge-api/test
git commit -m "feat(edge): expose revisioned mission and gate workflow"
```

### Task 5: Implement the read-only telemetry contract and replay gateway

**Files:**
- Create: `SMS/packages/telemetry/package.json`
- Create: `SMS/packages/telemetry/src/types.ts`
- Create: `SMS/packages/telemetry/src/gateway.ts`
- Create: `SMS/packages/telemetry/src/replay.ts`
- Create: `SMS/packages/telemetry/src/index.ts`
- Create: `SMS/apps/edge-api/src/routes/telemetry.ts`
- Test: `SMS/packages/telemetry/test/contract.test.ts`
- Test: `SMS/packages/telemetry/test/replay.test.ts`
- Test: `SMS/apps/edge-api/test/telemetry.test.ts`

**Interfaces:**
- `ReadOnlyTelemetryAdapter` and `CanonicalTelemetry` as defined above.
- `GET /api/revisions/:revisionId/telemetry/stream` — local authenticated event stream only.
- `POST /api/telemetry/replay` — imports a signed fixture/replay, never a command.

- [ ] **Step 1: Write compile-time and runtime no-C2 tests**

```ts
it("exposes only read methods", () => {
  const methods = Object.getOwnPropertyNames(ReadOnlyTelemetryAdapterFixture.prototype);
  expect(methods).not.toContain("sendCommand");
  expect(methods).not.toContain("arm");
  expect(methods).not.toContain("launch");
});

it("normalizes duplicate, delayed, malformed, and out-of-order telemetry safely", async () => {
  const events = await replayFixture([duplicate, delayed, malformed, valid]);
  expect(events.map((event) => event.eventId)).toEqual(["valid"]);
  expect(events.find(({ eventId }) => eventId === "malformed")?.status).toBe("rejected");
});
```

- [ ] **Step 2: Run tests to verify the adapter is absent**

Run: `cd SMS && npm test --workspace packages/telemetry -- --run && npm test --workspace apps/edge-api -- telemetry.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement canonical read-only adapter and replay**

Expose connect/read/subscribe/close only. Validate aircraft assignment, timestamps, units, position bounds, event IDs, source package IDs, ordering, and deduplication. Mark telemetry degraded on delay/dropout and preserve raw-event hashes and the applicable minimum one-year telemetry-retention record without storing payload imagery or intelligence content.

- [ ] **Step 4: Add isolated vendor adapter boundary**

Adapters may map approved status messages into `CanonicalTelemetry`; they may not import a command SDK, carry a command field, or expose a transport that can reach GCS control. Use synthetic/replay data for development and a one-way gateway contract for deployment.

- [ ] **Step 5: Run static no-C2 scans and commit**

Run: `cd SMS && npm test --workspace packages/telemetry -- --run && npm test --workspace apps/edge-api -- telemetry.test.ts --run && npm run verify:no-c2`
Expected: PASS; the scan fails if forbidden command identifiers or outbound command routes are introduced.

```bash
git add SMS/packages/telemetry SMS/apps/edge-api/src/routes/telemetry.ts SMS/apps/edge-api/test/telemetry.test.ts
git commit -m "feat(telemetry): add read-only canonical gateway"
```

### Task 6: Build the tactical console shell and visual system

**Files:**
- Create: `SMS/apps/console/package.json`
- Create: `SMS/apps/console/index.html`
- Create: `SMS/apps/console/src/main.tsx`
- Create: `SMS/apps/console/src/app/AppShell.tsx`
- Create: `SMS/apps/console/src/app/routes.tsx`
- Create: `SMS/apps/console/src/styles/tokens.css`
- Create: `SMS/apps/console/src/styles/operational.css`
- Create: `SMS/apps/console/src/i18n/registry.ts`
- Test: `SMS/apps/console/test/AppShell.test.tsx`
- Test: `SMS/apps/console/test/accessibility.test.tsx`

**Interfaces:**
- `AppShell` renders `/missions`, `/missions/:id/plan`, `/missions/:id/review`, `/missions/:id/monitor`, `/missions/:id/debrief`, `/sms`, and `/research` behind role checks.
- `useLocale()` changes labels only; it never changes API payloads or evaluator input.

- [ ] **Step 1: Write shell and accessibility tests**

```tsx
it("renders the controlled-data warning and keyboard-visible navigation", () => {
  render(<AppShell initialPath="/missions" />);
  expect(screen.getByText(/unclassified controlled safety metadata/i)).toBeVisible();
  expect(screen.getByRole("navigation")).toHaveAttribute("aria-label", "Mission navigation");
});

it("keeps Spanish and English decision concepts identical", () => {
  expect(renderConcepts("es")).toEqual(renderConcepts("en"));
});
```

- [ ] **Step 2: Run tests to verify missing console fails**

Run: `cd SMS && npm test --workspace apps/console -- --run`
Expected: FAIL.

- [ ] **Step 3: Implement local assets, tokens, and layout**

Use local font files and CSS variables for the specified palette. Build a map-first grid with the Mission Safety Strip, requirements panel, central map workspace, risk/aircraft/alert panel, and event/telemetry timeline. Include explicit text/icon/shape status, visible focus, large touch targets, reduced motion, and day/night themes. Do not add neon glows, radar sweeps, glassmorphism, or decorative animation.

- [ ] **Step 4: Run unit and axe tests**

Run: `cd SMS && npm test --workspace apps/console -- --run`
Expected: PASS with no critical axe violations and no locale-dependent rule changes.

- [ ] **Step 5: Commit**

```bash
git add SMS/apps/console
git commit -m "feat(console): add aviation day-night workstation shell"
```

### Task 7: Implement Mission Safety Strip, gates, checklists, and alert timeline

**Files:**
- Create: `SMS/apps/console/src/components/MissionSafetyStrip.tsx`
- Create: `SMS/apps/console/src/components/GateStatus.tsx`
- Create: `SMS/apps/console/src/components/ChecklistPanel.tsx`
- Create: `SMS/apps/console/src/components/AlertTimeline.tsx`
- Create: `SMS/apps/console/src/hooks/useMissionSafety.ts`
- Test: `SMS/apps/console/test/MissionSafetyStrip.test.tsx`
- Test: `SMS/apps/console/test/ChecklistPanel.test.tsx`

**Interfaces:**
- `MissionSafetyStrip({ mission, safetyResult, gates, locale }): JSX.Element`
- `ChecklistPanel({ items, onRespond }): JSX.Element`
- `GateStatus({ gate, decision, requiredRole }): JSX.Element`

- [ ] **Step 1: Write component behavior tests**

```tsx
it("shows phase, class, flight rule, four gates, highest blocker, freshness, and operator state", () => {
  render(<MissionSafetyStrip {...blockedMissionProps} />);
  expect(screen.getByText("IA")).toBeVisible();
  expect(screen.getByText(/configuration out of scope/i)).toBeVisible();
  expect(screen.getAllByRole("status")).toHaveLength(4);
});

it("does not render a check-all control", () => {
  render(<ChecklistPanel {...checklistProps} />);
  expect(screen.queryByRole("button", { name: /check all|complete all/i })).toBeNull();
});
```

- [ ] **Step 2: Run tests to verify missing components fail**

Run: `cd SMS && npm test --workspace apps/console -- MissionSafetyStrip.test.tsx ChecklistPanel.test.tsx --run`
Expected: FAIL.

- [ ] **Step 3: Implement the persistent strip and evidence drill-down**

Selecting a segment opens the governing requirement, Spanish source excerpt, controlled English translation, source edition/section, freshness, evidence hash, and reviewer status. Blocked/conditional/degraded states use text, icon, shape, and color together. The strip remains visible across planning, review, monitoring, and debrief.

- [ ] **Step 4: Implement item-by-item checklist and gate action UI**

Every response records accountable identity, UTC timestamp, evidence, and optional reason. Gate action buttons are shown only for the authorized role and disabled when kernel blockers/dependencies are unresolved. Operator go/no-go and abort controls remain explicit and cannot be overridden by commander status.

- [ ] **Step 5: Run tests and commit**

Run: `cd SMS && npm test --workspace apps/console -- MissionSafetyStrip.test.tsx ChecklistPanel.test.tsx --run`
Expected: PASS.

```bash
git add SMS/apps/console/src/components SMS/apps/console/src/hooks SMS/apps/console/test
git commit -m "feat(console): add mission strip and gate review controls"
```

### Task 8: Integrate offline map, planning, monitoring, and telemetry views

**Files:**
- Create: `SMS/apps/console/src/components/MapWorkspace.tsx`
- Create: `SMS/apps/console/src/components/TelemetryPanel.tsx`
- Create: `SMS/apps/console/src/components/RiskPanel.tsx`
- Create: `SMS/apps/console/src/lib/local-map.ts`
- Create: `SMS/apps/console/src/hooks/useTelemetry.ts`
- Modify: `SMS/apps/console/src/app/routes.tsx`
- Test: `SMS/apps/console/test/MapWorkspace.test.tsx`
- Test: `SMS/apps/console/test/TelemetryPanel.test.tsx`
- Test: `SMS/apps/console/e2e/offline-mission.spec.ts`

**Interfaces:**
- `MapWorkspace({ packageDirectory, route, findings, mode }): JSX.Element`
- `TelemetryPanel({ aircraft, telemetry, degraded }): JSX.Element`
- `useTelemetry(revisionId): { events, status, acknowledge }`

- [ ] **Step 1: Write offline map and telemetry tests**

```tsx
it("renders a local map source without fetching a remote tile URL", async () => {
  render(<MapWorkspace {...fixtureMapProps} />);
  await screen.findByTestId("map-canvas");
  expect(globalThis.fetch).not.toHaveBeenCalledWith(expect.stringMatching(/^https?:\/\//));
});

it("shows degraded telemetry and preserves the approved reserve", () => {
  render(<TelemetryPanel {...droppedLinkProps} />);
  expect(screen.getByText(/telemetry degraded/i)).toBeVisible();
  expect(screen.getByText(/approved minimum reserve/i)).toBeVisible();
});
```

- [ ] **Step 2: Run focused tests to verify missing view fails**

Run: `cd SMS && npm test --workspace apps/console -- MapWorkspace.test.tsx TelemetryPanel.test.tsx --run`
Expected: FAIL.

- [ ] **Step 3: Implement local MapLibre/PMTiles loading**

Resolve package manifests from the edge API, verify hashes before mounting sources, and use a local protocol/file loader. Render terrain, contours/hillshade, roads/hydrography/settlements, official airspace/obstacles/AIP, weather/NOTAM, route, emergency sites, VLOS/viewshed, C2 coverage-risk, and population-exposure overlays with visible source/freshness labels.

- [ ] **Step 4: Implement planning interactions**

Support waypoint/route drawing, corridors, holds/orbits, area-search patterns, altitude profiles, emergency/alternate/recovery sites, route checks, and draft PDF/JSON/GeoJSON/KML/KMZ/GPX exports. Detailed route construction is workstation-optimized; tablet layout remains review/checklist oriented.

- [ ] **Step 5: Implement read-only monitoring cards and event timeline**

Display position, altitude/height, heading, groundspeed, vertical rate, active leg/deviation, energy/reserve, battery health, platform health, link latency/loss, GNSS, DAA/ADS-B/transponder status when available, weather deterioration, alert acknowledgment, and action status. No card may contain a control or command action.

- [ ] **Step 6: Run Playwright disconnected E2E and commit**

Run: `cd SMS && npm run test:e2e --workspace apps/console -- e2e/offline-mission.spec.ts`
Expected: PASS while network requests are blocked; mission planning, map display, gate review, telemetry replay, and export remain usable.

```bash
git add SMS/apps/console/src SMS/apps/console/test SMS/apps/console/e2e
git commit -m "feat(console): add offline map planning and monitoring"
```

### Task 9: Implement signed package import, export, and safe failure states

**Files:**
- Create: `SMS/apps/edge-api/src/routes/packages.ts`
- Create: `SMS/apps/edge-api/src/routes/exports.ts`
- Create: `SMS/apps/edge-api/src/services/safe-mode.ts`
- Test: `SMS/apps/edge-api/test/packages.test.ts`
- Test: `SMS/apps/edge-api/test/exports.test.ts`
- Test: `SMS/apps/edge-api/test/safe-mode.test.ts`

**Interfaces:**
- `POST /api/packages/import`
- `GET /api/packages/quarantine`
- `POST /api/revisions/:revisionId/export`
- `POST /api/mission-import/review`

- [ ] **Step 1: Write tamper, missing-data, database-failure, and import tests**

```ts
it("quarantines an unsigned or downgraded package", async () => {
  const response = await importPackage(unsignedOrOlderPackage);
  expect(response.statusCode).toBe(422);
  expect(response.json().state).toBe("quarantined");
});

it("keeps a mission unchanged when export fails", async () => {
  await simulateExportFailure();
  const before = await getRevision(id);
  expect((await exportRevision(id)).statusCode).toBe(500);
  expect(await getRevision(id)).toEqual(before);
});
```

- [ ] **Step 2: Run tests to verify absent safe-mode behavior fails**

Run: `cd SMS && npm test --workspace apps/edge-api -- packages.test.ts exports.test.ts safe-mode.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement package verification and quarantine**

Verify signatures, hashes, schema, issuer, dependencies, expiry, geographic scope, and no-downgrade before activation. Keep imported missions read-only until explicitly cloned; preserve historical package snapshots.

- [ ] **Step 4: Implement bilingual export/import**

Export mission/revision, profile/policy, aircraft/GCS/payload/battery/crew, route and package references, rule evaluations, checklists/evidence, hazards/risks/exceptions, gates, events/telemetry indexes, debrief, occurrences, audit manifest, and hashes. Research exports use separate endpoints and schemas.

- [ ] **Step 5: Implement safe failure behavior**

Unknown/conflicting regulation, invalid critical data, clock inconsistency, missing map/terrain, telemetry loss, database write failure, kernel failure, translation missing, and export failure each display a distinct status and disable only affected actions while preserving audit context.

- [ ] **Step 6: Run tests and commit**

Run: `cd SMS && npm test --workspace apps/edge-api -- packages.test.ts exports.test.ts safe-mode.test.ts --run`
Expected: PASS; no recovery silently recreates an approval.

```bash
git add SMS/apps/edge-api/src/routes/packages.ts SMS/apps/edge-api/src/routes/exports.ts SMS/apps/edge-api/src/services/safe-mode.ts SMS/apps/edge-api/test
git commit -m "feat(edge): add signed package and safe failure workflows"
```

## P4 Completion Evidence

P4 is complete when a headless edge node and local clients operate with internet blocked, four gates and role permissions are enforced, the Mission Safety Strip stays visible, signed packages and mission exports round-trip, read-only telemetry replays and degrades safely, and static/runtime checks prove that no C2 command path exists.
