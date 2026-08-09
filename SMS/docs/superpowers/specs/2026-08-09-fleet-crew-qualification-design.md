# Fleet Crew Qualification and Staffing Design

**Date:** 2026-08-09

**Status:** Approved for implementation

## Goal

Add deterministic, privacy-minimized fleet predicates for crew qualification, recency, duty and rest, cumulative workload, screen exposure, self-declared operational safety status, and one-independent-operator-per-aircraft staffing.

The feature prepares auditable fleet facts for later safety-kernel integration. It does not change mission release behavior in this slice.

## Scope

Create one pure module, `packages/fleet/src/qualification.ts`, export it from the fleet package, and cover it with focused tests. The module has no storage, network, user-interface, or GCS/aircraft command behavior.

In scope:

- Verify assignment identity, role, and operator-to-aircraft assignment.
- Verify the required qualification edition, qualification validity, and recency validity.
- Evaluate elapsed duty, preceding rest, cumulative workload, and cumulative screen exposure against an explicit versioned policy.
- Reduce the crew member's self-declared operational status without carrying a reason or clinical information.
- Detect missing, multiple, unqualified, and non-independent operator staffing.
- Return stable blocker codes and evidence references.

Out of scope:

- Medical clearance, diagnosis, symptoms, medical notes, or clinical reasoning.
- Human-subject research records or research-derived fitness decisions.
- Safety-kernel mission integration, gate invalidation, persistence, and UI presentation.
- Inventing regulatory or institutional numeric limits. Every duration threshold is supplied by a reviewed policy input.

## Public interfaces

The module exports:

```ts
export function evaluateCrewAssignment(input: CrewAssignmentEvaluationInput): CrewEvaluation;

export function evaluateDutyAndRest(
  dutyPeriod: DutyPeriod,
  policy: DutyPolicy,
  nowUtc: string,
): DutyEvaluation;

export function requireOneOperatorPerAircraft(
  assignments: readonly StaffingAssignment[],
  requiredAircraftIds?: readonly string[],
): SafetyBlocker[];
```

`CrewEvaluation` and `DutyEvaluation` contain only:

- `status`: `available`, `restricted`, `unavailable`, or `unknown`.
- `blockers`: stable `SafetyBlocker` values.
- `evidenceRefs`: trimmed, de-duplicated evidence identifiers in first-seen order.

No input object, free-text self-declaration, or medical field is copied into a result.

## Input model

A crew assignment identifies the user, role, optional aircraft, required qualification edition, and assignment evidence. Operators require an aircraft identifier. A qualification record identifies the same user and role, names its edition, gives qualification and recency validity end instants, and supplies evidence.

A duty period records its UTC start, the prior duty's UTC end, cumulative workload minutes, cumulative screen-exposure minutes, and evidence. A duty policy supplies nonnegative finite limits for maximum duty, minimum rest, maximum cumulative workload, and maximum cumulative screen exposure, together with policy identity, edition, and evidence.

The only self-declared personnel fact accepted by the evaluator is one of the four operational statuses. There is intentionally no field for a reason, diagnosis, symptom, medical note, or clinical assessment.

`StaffingAssignment` remains a small mission-facing projection: aircraft, role, user, qualification boolean, and optional evidence. `requiredAircraftIds` lets the caller identify active aircraft that have no crew rows at all. When omitted, the function checks every aircraft represented by the assignments.

## Decision rules

### UTC and numeric validity

UTC inputs must be real ISO-8601 instants ending in `Z`. Numeric limits and accumulated minutes must be finite and nonnegative. Invalid reference time, policy, duty, qualification, or recency data produces an `unknown` status and a data-severity blocker. The evaluator never guesses or normalizes malformed facts. Independently valid dimensions are still evaluated so one malformed timestamp cannot hide a known expiry or limit violation.

### Qualification and recency

- A missing qualification record is `unknown`.
- User or role mismatch, stale edition, qualification expiry, or recency expiry is `unavailable`.
- A validity end is exclusive: `nowUtc >= validUntilUtc` is expired. This makes the exact boundary deterministic.
- Qualification evidence must contain at least one nonblank reference; otherwise qualification status is `unknown` unless another definitive unavailable condition also applies.

### Duty, rest, workload, and screen exposure

- Duty minutes are the elapsed minutes from `startedAtUtc` through `nowUtc`.
- Rest minutes are the elapsed minutes from `previousDutyEndedAtUtc` through `startedAtUtc`.
- Duty at exactly the maximum and rest at exactly the minimum are allowed.
- Exceeding maximum duty or falling below minimum rest is `unavailable`.
- Exceeding cumulative workload or cumulative screen exposure is `restricted`.
- Workload and screen exposure at exactly their maxima are allowed.
- Missing policy or duty inputs in `evaluateCrewAssignment` is `unknown`.
- Duty and policy evidence must be present; missing evidence is `unknown` unless a definitive unavailable condition also applies.

### Self-declared operational status

- `available` adds no blocker.
- `restricted`, `unavailable`, and `unknown` preserve their respective status using stable blocker codes.
- The result does not contain a reason or echo the input object.

### Status precedence

When several rules apply, status precedence is:

1. `unavailable`
2. `unknown`
3. `restricted`
4. `available`

All detected blockers remain visible even when a higher-precedence status determines the result.

### One operator per aircraft

For every required aircraft:

- No operator row produces `OPERATOR_ASSIGNMENT_MISSING`.
- More than one operator row produces `MULTIPLE_OPERATORS_ASSIGNED_TO_AIRCRAFT`.
- A sole operator whose qualification projection is false produces `QUALIFIED_OPERATOR_REQUIRED`.
- One user assigned as operator to more than one distinct aircraft produces one `OPERATOR_ASSIGNED_TO_MULTIPLE_AIRCRAFT` blocker for that user.
- Blank or whitespace-wrapped assignment and required-aircraft identities produce `CREW_ASSIGNMENT_INVALID`; malformed identities are rejected rather than normalized or silently ignored.

Blocker order is deterministic: malformed assignment data, per-aircraft coverage in sorted aircraft order, then duplicate users in sorted user order.

## Evidence and privacy

Evidence identifiers are operational metadata, not narrative personnel data. The evaluator emits only identifiers already present on assignment, qualification, duty, policy, or staffing projections. It trims blank values and removes duplicates without changing first-seen order.

The public input types contain no medical or clinical fields. Runtime objects may carry unrelated extra properties because JavaScript is structurally open, but evaluation constructs a new minimal result and cannot pass those properties through.

## Testing

Focused tests cover:

- A complete available assignment.
- Missing qualification and missing duty/policy facts.
- User, role, aircraft, edition, qualification expiry, and recency failures.
- Exact qualification, recency, duty, rest, workload, and screen boundaries.
- Invalid UTC and invalid numeric facts.
- Restricted, unavailable, and unknown self-declarations.
- Missing evidence and deterministic evidence reduction.
- Missing, multiple, unqualified, and duplicate operator assignments.
- Privacy by proving arbitrary diagnosis and clinical-reasoning properties never appear in serialized output.
- Public export from the fleet package.

The focused fleet test, fleet typecheck/build, root typecheck, and complete root test suite must pass before the branch is published.
