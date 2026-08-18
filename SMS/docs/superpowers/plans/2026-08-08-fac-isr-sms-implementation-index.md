# FAC ISR Safety Management Suite Implementation Plan Index

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement these plans task-by-task. Each task ends with an independent test or evidence check.

**Goal:** Build the approved bilingual, offline-first FAC ISR safety decision-support suite for unarmed UAS/RPAS operations under AAAES and RACAE, with a deterministic safety kernel, four-gate release workflow, read-only monitoring, human-performance research separation, and signed portable evidence.

**Architecture:** A new TypeScript workspace under `SMS/` is split into pure domain packages and a deployable edge service. The safety kernel has no UI or network dependencies; the tactical console consumes its deterministic results through a local API. Operational and research data are separate stores and permission domains. A connected staging tool produces signed regulatory, map, and policy packages for import into an isolated edge node.

**Tech Stack:** Node.js 22 LTS; TypeScript 5.7+ in strict mode; npm workspaces; Fastify; React + Vite; SQLite with Drizzle ORM; Zod; MapLibre GL JS; PMTiles; Turf; Vitest; fast-check; Playwright; axe-core; OpenTelemetry-compatible structured logs; Ed25519 package signatures; Docker/OCI for headless deployment.

## Global Constraints

- Create a new `SMS/` TypeScript workspace; do not extend the existing MATB web UI.
- The first operational profile is Colombian State Aviation / FAC ISR under AAAES and RACAE; future profiles are Private Certified Operator, then Civil Public Entity.
- The application is safety decision support only and has no command, arm, launch, redirect, payload-control, or recovery-control path.
- Only unarmed ISR and support configurations are in the operational safety case; armed or strike configurations are hard-blocked.
- One qualified operator or remote pilot is required per active aircraft; swarm behavior is isolated research-only and permanently non-dispatchable.
- The first release handles unclassified controlled safety metadata only; never store ISR imagery, intelligence products, weapons data, or classified content.
- The edge node must plan, review, monitor, debrief, and export without internet access.
- Critical data packages are signed, hashed, versioned, freshness-checked, and protected against unauthorized downgrade.
- Spanish is the authoritative operational source language; English is a controlled translation. Language changes cannot alter rule behavior, units, or stored meaning.
- UTC is authoritative for operations; `America/Bogota` is supplementary display time.
- Every release decision traces to an authoritative source, edition, section, effective date, normalized interpretation, and evidence snapshot.
- Four gates are separate: maintenance, each operator/PIC, safety, and commander; the operator retains final go/no-go and abort authority.
- Unknown, stale, conflicting, unsigned, corrupt, or missing critical evidence fails closed or requires a controlled, time-bounded exception.
- Operational human-performance controls may record minimum safety status; medical diagnoses and automated fitness-to-fly decisions are out of scope.
- Research protocols, consent, participant identities, and research events remain physically and logically separated from operational records.
- Product authorship metadata is `Dr Diego Malpica — Aerospace Medicine and Human Performance — Subdirectorate of Aerospace Sciences — Colombian Aerospace Force`.
- No implementation task may claim operational acceptance; qualified FAC and competent-authority review remains a release prerequisite.

## Plan Set and Dependencies

| Plan | Deliverable | Depends on | Independently testable result |
| --- | --- | --- | --- |
| [P0 Evidence and regulatory corpus](2026-08-08-evidence-regulatory-corpus.md) | Source register, immutable originals, normalized evidence package, research provenance | None | A signed corpus can be verified offline and every requirement has provenance |
| [P1 Safety kernel and release](2026-08-08-safety-kernel-and-release.md) | Deterministic applicability, rule, lifecycle, dependency, and four-gate engine | P0 schemas | Golden missions produce correct ready/blocked/conditional states |
| [P2 Fleet, maintenance, and energy](2026-08-08-fleet-maintenance-energy.md) | Aircraft, configuration, qualification, maintenance, battery, capability, and reserve models | P1 contracts | Energy and maintenance blockers are reproducible from fixture inputs |
| [P3 Offline geospatial planning](2026-08-08-offline-geospatial-planning.md) | Signed map packages, coordinates, terrain, airspace, route, VLOS/BVLOS, and flight-plan drafting | P0 manifests, P1 evaluation contracts | A disconnected workstation validates a route against fixture layers |
| [P4 Edge service, console, and telemetry](2026-08-08-edge-console-telemetry.md) | Headless edge API, local auth, audit ledger, map-first console, and read-only telemetry | P1/P2/P3 packages | A local client completes a four-gate mission workflow without network access or C2 methods |
| [P5 SMS and human-performance research](2026-08-08-sms-human-performance-research.md) | Hazards, CAPA, audits, MOC, operational controls, and isolated research laboratory | P1/P4 data contracts | Operational and research fixtures cannot cross boundaries; SMS workflows are auditable |
| [P6 Verification and deployment](2026-08-08-verification-deployment.md) | Offline OCI deployment, signed release, SBOM, test matrix, security negatives, and acceptance evidence | P0–P5 | A clean headless install passes offline, tamper, accessibility, and no-C2 verification |
| [P7 Future operator profiles](2026-08-08-future-operator-profiles.md) | RAC 100 Private Certified Operator, then Civil Public Entity profiles | P0–P6 accepted State Aviation baseline | Profile-specific rules and roles change applicability without changing kernel semantics |

## Execution Order

1. Execute P0 and obtain the evidence-review gate. No regulatory interpretation is promoted into an active policy package before qualified review.
2. Execute P1 with deliberately incomplete policy fixtures first; the kernel must block until an approved risk matrix and delegated authorities are imported.
3. Execute P2 and P3 in parallel after their shared contracts are stable; each remains usable without the console.
4. Execute P4 against synthetic fixtures and read-only telemetry replays. Keep the command-path negative tests active throughout.
5. Execute P5 only after the operational/research storage boundary is enforced by P4.
6. Execute P6 as the integration and acceptance gate for the State Aviation baseline.
7. Execute P7 only after FAC/AAAES acceptance of the State Aviation baseline and a documented change-impact review.

## Cross-Plan Interface Rules

```ts
export type PackageId = string & { readonly __brand: "PackageId" };
export type MissionId = string & { readonly __brand: "MissionId" };
export type MissionRevisionId = string & { readonly __brand: "MissionRevisionId" };

export interface SignedPackageManifest {
  packageId: PackageId;
  kind: "regulatory" | "policy" | "map" | "weather" | "notam" | "terminology" | "software";
  issuer: string;
  version: string;
  issuedAtUtc: string;
  effectiveFromUtc: string;
  expiresAtUtc?: string;
  geographicScope?: string;
  contentSha256: string;
  signature: string;
  keyId: string;
  dependencies: PackageId[];
}

export interface SafetyEvaluationResult {
  missionRevisionId: MissionRevisionId;
  status: "ready" | "conditional" | "blocked" | "degraded";
  evaluations: readonly RuleEvaluation[];
  blockers: readonly SafetyBlocker[];
  invalidatedGates: readonly GateName[];
  kernelVersion: string;
}
```

No plan may introduce a second shape for these identifiers or bypass signature and snapshot validation.

## Shared Verification Commands

Run from `SMS/` after workspace setup:

```bash
npm ci
npm run typecheck --workspaces
npm run test --workspaces -- --run
npm run lint --workspaces
npm run test:e2e --workspace apps/console
npm run verify:offline
npm run verify:no-c2
```

Expected clean-build evidence is recorded in the release manifest, not only in terminal output.
