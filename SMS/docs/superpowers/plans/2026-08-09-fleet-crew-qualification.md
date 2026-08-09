# Fleet Crew Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic, privacy-minimized crew qualification, duty/rest, workload, screen-exposure, and one-operator-per-aircraft checks to `@fac-isr/fleet`.

**Architecture:** A single pure fleet module owns the operational crew input and result contracts, UTC and evidence reduction helpers, status aggregation, and staffing predicates. It returns safety-kernel blocker projections but does not integrate those facts into mission release yet.

**Tech Stack:** TypeScript 5.7, Node.js 22, Vitest 2, npm workspaces.

## Global Constraints

- Validity end instants are exclusive: equality with `nowUtc` is expired.
- Exact duty, rest, workload, and screen-exposure policy limits are allowed.
- Status precedence is `unavailable`, `unknown`, `restricted`, `available`.
- Numeric thresholds come only from explicit policy inputs; no regulatory values are embedded.
- Operational output contains only status, blockers, and evidence identifiers.
- No diagnosis, symptom, medical note, clinical reasoning, research record, GCS command, or aircraft command is represented.
- Safety-kernel mission integration is deferred to the fleet/energy integration task.

---

### Task 1: Duty, rest, workload, and screen-exposure evaluation

**Files:**

- Create: `SMS/packages/fleet/src/qualification.ts`
- Create: `SMS/packages/fleet/test/qualification.test.ts`

**Interfaces:**

- Consumes: `SafetyBlocker` from `@fac-isr/safety-kernel` as a type-only import.
- Produces: `OperationalCrewStatus`, `DutyPeriod`, `DutyPolicy`, `DutyEvaluation`, and `evaluateDutyAndRest(dutyPeriod, policy, nowUtc)`.

- [ ] **Step 1: Write the failing duty boundary tests**

Create `qualification.test.ts` with literal UTC fixtures and these observable cases:

```ts
import { describe, expect, it } from "vitest";
import { evaluateDutyAndRest } from "../src/qualification.js";

const policy = {
  policyId: "crew-policy",
  edition: "2026.1",
  maxDutyMinutes: 480,
  minimumRestMinutes: 720,
  maxCumulativeWorkloadMinutes: 300,
  maxScreenExposureMinutes: 240,
  evidenceRefs: ["policy-ev"],
};

const duty = {
  startedAtUtc: "2026-08-09T00:00:00Z",
  previousDutyEndedAtUtc: "2026-08-08T12:00:00Z",
  cumulativeWorkloadMinutes: 300,
  cumulativeScreenExposureMinutes: 240,
  evidenceRefs: ["duty-ev"],
};

describe("crew duty and rest", () => {
  it("allows exact duty, rest, workload, and screen limits", () => {
    expect(evaluateDutyAndRest(duty, policy, "2026-08-09T08:00:00Z")).toEqual({
      status: "available",
      blockers: [],
      evidenceRefs: ["duty-ev", "policy-ev"],
    });
  });

  it("makes excessive duty and insufficient rest unavailable", () => {
    expect(evaluateDutyAndRest(duty, policy, "2026-08-09T08:00:00.001Z").status).toBe("unavailable");
    expect(evaluateDutyAndRest({ ...duty, previousDutyEndedAtUtc: "2026-08-08T12:00:00.001Z" }, policy, "2026-08-09T08:00:00Z").status).toBe("unavailable");
  });

  it("restricts excessive workload and screen exposure", () => {
    expect(evaluateDutyAndRest({ ...duty, cumulativeWorkloadMinutes: 301 }, policy, "2026-08-09T07:59:00Z").status).toBe("restricted");
    expect(evaluateDutyAndRest({ ...duty, cumulativeScreenExposureMinutes: 241 }, policy, "2026-08-09T07:59:00Z").status).toBe("restricted");
  });

  it("returns unknown for malformed time, numeric, or evidence facts", () => {
    expect(evaluateDutyAndRest(duty, policy, "2026-02-30T00:00:00Z").status).toBe("unknown");
    expect(evaluateDutyAndRest({ ...duty, cumulativeWorkloadMinutes: Number.NaN }, policy, "2026-08-09T07:59:00Z").status).toBe("unknown");
    expect(evaluateDutyAndRest({ ...duty, evidenceRefs: [] }, policy, "2026-08-09T07:59:00Z").status).toBe("unknown");
  });
});
```

The production changes that make these tests fail are reversed inequalities, accepting malformed values, or omitting evidence validation.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `cd SMS && npm test --workspace @fac-isr/fleet -- qualification.test.ts --run`

Expected: FAIL because `../src/qualification.js` does not exist.

- [ ] **Step 3: Implement the minimal duty contracts and evaluator**

Create `qualification.ts` with these public contracts:

```ts
import type { SafetyBlocker } from "@fac-isr/safety-kernel";

export type OperationalCrewStatus = "available" | "restricted" | "unavailable" | "unknown";

export interface DutyPeriod {
  startedAtUtc: string;
  previousDutyEndedAtUtc: string;
  cumulativeWorkloadMinutes: number;
  cumulativeScreenExposureMinutes: number;
  evidenceRefs: readonly string[];
}

export interface DutyPolicy {
  policyId: string;
  edition: string;
  maxDutyMinutes: number;
  minimumRestMinutes: number;
  maxCumulativeWorkloadMinutes: number;
  maxScreenExposureMinutes: number;
  evidenceRefs: readonly string[];
}

export interface DutyEvaluation {
  status: OperationalCrewStatus;
  blockers: readonly SafetyBlocker[];
  evidenceRefs: readonly string[];
}
```

Add strict UTC parsing, finite-nonnegative numeric checks, stable blocker construction, first-seen evidence reduction, and status precedence. Compute duty and rest in milliseconds to preserve the exact one-millisecond boundary in the tests. Use `>` for maximum limits and `<` for minimum rest.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `cd SMS && npm test --workspace @fac-isr/fleet -- qualification.test.ts --run`

Expected: PASS with four duty/rest tests.

- [ ] **Step 5: Refactor helpers while green**

Extract only helpers shared by later assignment evaluation: `parseUtc`, `isFiniteNonnegative`, `createBlocker`, `collectEvidence`, and `resolveStatus`. Keep them module-private and rerun the focused test.

Run: `cd SMS && npm test --workspace @fac-isr/fleet -- qualification.test.ts --run`

Expected: PASS.

### Task 2: Qualification, recency, assignment, and privacy evaluation

**Files:**

- Modify: `SMS/packages/fleet/src/qualification.ts`
- Modify: `SMS/packages/fleet/test/qualification.test.ts`

**Interfaces:**

- Consumes: `DutyPeriod`, `DutyPolicy`, `DutyEvaluation`, and `evaluateDutyAndRest` from Task 1.
- Produces: `CrewRole`, `QualificationRecord`, `CrewAssignmentEvaluationInput`, `CrewEvaluation`, and `evaluateCrewAssignment(input)`.

- [ ] **Step 1: Write the failing available, expiry, missing-data, and privacy tests**

Append literal fixtures with an operator assigned to `A-1`, qualification edition `2026.1`, qualification validity `2026-12-01T00:00:00Z`, recency validity `2026-09-01T00:00:00Z`, the Task 1 duty and policy, and self-declared status `available`.

Add these assertions:

```ts
it("returns a minimal available evaluation for current qualification and duty", () => {
  expect(evaluateCrewAssignment(input)).toEqual({
    status: "available",
    blockers: [],
    evidenceRefs: ["assignment-ev", "qualification-ev", "duty-ev", "policy-ev"],
  });
});

it.each([
  ["qualification", { validUntilUtc: "2026-08-09T08:00:00Z" }, "QUALIFICATION_EXPIRED"],
  ["recency", { recencyValidUntilUtc: "2026-08-09T08:00:00Z" }, "RECENCY_EXPIRED"],
])("blocks at the exact %s expiry instant", (_name, qualificationChange, code) => {
  const result = evaluateCrewAssignment({
    ...input,
    qualification: { ...input.qualification!, ...qualificationChange },
  });
  expect(result.status).toBe("unavailable");
  expect(result.blockers).toContainEqual(expect.objectContaining({ code }));
});

it("returns unknown when qualification or duty facts are absent", () => {
  expect(evaluateCrewAssignment({ ...input, qualification: undefined }).status).toBe("unknown");
  expect(evaluateCrewAssignment({ ...input, dutyPeriod: undefined }).status).toBe("unknown");
});

it("does not expose diagnosis or clinical reasoning from runtime input", () => {
  const runtimeInput = { ...input, diagnosis: "private", clinicalReasoning: "private" };
  const serialized = JSON.stringify(evaluateCrewAssignment(runtimeInput));
  expect(serialized).not.toContain("diagnosis");
  expect(serialized).not.toContain("clinicalReasoning");
  expect(serialized).not.toContain("private");
});
```

Also add one table covering user mismatch, role mismatch, missing operator aircraft, stale qualification edition, missing qualification evidence, and all four self-declared statuses. Assert literal status and blocker code for every row.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `cd SMS && npm test --workspace @fac-isr/fleet -- qualification.test.ts --run`

Expected: FAIL because `evaluateCrewAssignment` is not exported.

- [ ] **Step 3: Implement the assignment contracts and evaluator**

Use these contracts:

```ts
export type CrewRole = "operator" | "observer" | "maintainer" | "safety" | "commander";

export interface QualificationRecord {
  userId: string;
  role: CrewRole;
  edition: string;
  validUntilUtc: string;
  recencyValidUntilUtc: string;
  evidenceRefs: readonly string[];
}

export interface CrewAssignmentEvaluationInput {
  assignment: {
    userId: string;
    role: CrewRole;
    aircraftId?: string;
    requiredQualificationEdition: string;
    evidenceRefs: readonly string[];
  };
  qualification?: QualificationRecord;
  dutyPeriod?: DutyPeriod;
  dutyPolicy?: DutyPolicy;
  operationalSafetyStatus: OperationalCrewStatus;
  nowUtc: string;
}

export interface CrewEvaluation {
  status: OperationalCrewStatus;
  blockers: readonly SafetyBlocker[];
  evidenceRefs: readonly string[];
}
```

Construct a new result from the declared fields. Never spread the input into output. Apply all checks so every detected blocker remains visible, then choose status using the documented precedence.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `cd SMS && npm test --workspace @fac-isr/fleet -- qualification.test.ts --run`

Expected: PASS for assignment, expiry, missing-data, status-precedence, and privacy cases.

### Task 3: Independent operator staffing and package export

**Files:**

- Modify: `SMS/packages/fleet/src/qualification.ts`
- Modify: `SMS/packages/fleet/src/index.ts`
- Modify: `SMS/packages/fleet/test/qualification.test.ts`

**Interfaces:**

- Consumes: `CrewRole`, module-private blocker/evidence helpers, and safety-kernel `SafetyBlocker`.
- Produces: `StaffingAssignment` and `requireOneOperatorPerAircraft(assignments, requiredAircraftIds?)` through the fleet package export.

- [ ] **Step 1: Write the failing staffing tests**

Add tests for the old roadmap case and complete aircraft coverage:

```ts
it("blocks one operator assigned to multiple aircraft", () => {
  expect(requireOneOperatorPerAircraft([
    { aircraftId: "A-1", role: "operator", userId: "U-1", qualified: true },
    { aircraftId: "A-2", role: "operator", userId: "U-1", qualified: true },
  ])).toContainEqual(expect.objectContaining({ code: "OPERATOR_ASSIGNED_TO_MULTIPLE_AIRCRAFT" }));
});

it("blocks missing, multiple, and unqualified operator coverage", () => {
  const assignments = [
    { aircraftId: "A-1", role: "observer" as const, userId: "O-1", qualified: true },
    { aircraftId: "A-2", role: "operator" as const, userId: "U-1", qualified: false },
    { aircraftId: "A-3", role: "operator" as const, userId: "U-2", qualified: true },
    { aircraftId: "A-3", role: "operator" as const, userId: "U-3", qualified: true },
  ];
  expect(requireOneOperatorPerAircraft(assignments, ["A-1", "A-2", "A-3", "A-4"]).map(({ code }) => code)).toEqual([
    "OPERATOR_ASSIGNMENT_MISSING",
    "QUALIFIED_OPERATOR_REQUIRED",
    "MULTIPLE_OPERATORS_ASSIGNED_TO_AIRCRAFT",
    "OPERATOR_ASSIGNMENT_MISSING",
  ]);
});
```

Add a loop that assigns every user to every pair of distinct aircraft and asserts the duplicate-user blocker. Add a valid two-aircraft/two-operator case that returns `[]`, a malformed blank-identity case, and an import from `../src/index.js` proving the public export.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `cd SMS && npm test --workspace @fac-isr/fleet -- qualification.test.ts --run`

Expected: FAIL because the staffing predicate is absent.

- [ ] **Step 3: Implement deterministic staffing checks and export the module**

Add:

```ts
export interface StaffingAssignment {
  aircraftId: string;
  role: CrewRole;
  userId: string;
  qualified: boolean;
  evidenceRefs?: readonly string[];
}
```

Validate blank identifiers first. Build the required aircraft set from `requiredAircraftIds` when supplied, otherwise from assignment aircraft IDs. Sort unique aircraft IDs and user IDs before emitting coverage and duplicate-user blockers. A valid aircraft has exactly one operator row and that row has `qualified: true`.

Add `export * from "./qualification.js";` to `src/index.ts`.

- [ ] **Step 4: Run focused and package verification**

Run:

```bash
cd SMS
npm test --workspace @fac-isr/fleet -- qualification.test.ts --run
npm run typecheck --workspace @fac-isr/fleet
npm run build --workspace @fac-isr/fleet
```

Expected: all commands PASS.

- [ ] **Step 5: Run repository verification**

Run:

```bash
cd SMS
npm run typecheck
npm test -- --run
```

Expected: all TypeScript projects pass and every Vitest suite passes after the root pretest build.

- [ ] **Step 6: Review and commit**

Run `git diff --check`, inspect `git diff --stat` and `git status --short`, then commit only the spec, plan, qualification module, fleet index, and qualification test:

```bash
git add SMS/docs/superpowers/specs/2026-08-09-fleet-crew-qualification-design.md SMS/docs/superpowers/plans/2026-08-09-fleet-crew-qualification.md SMS/packages/fleet/src/qualification.ts SMS/packages/fleet/src/index.ts SMS/packages/fleet/test/qualification.test.ts
git commit -m "feat(fleet): enforce crew qualification and staffing"
```
