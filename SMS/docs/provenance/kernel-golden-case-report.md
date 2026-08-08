# Safety-kernel golden case report

These fixtures are deterministic verification inputs only. They do not constitute qualified FAC/AAAES review, operational acceptance, or approval of any RACAE interpretation.

## Coverage

`all-racae-classes.json` covers IA, IB, IC, II, and III with unarmed ISR/support VFR/VLOS cases, an IC IFR case requiring explicit segregated-airspace, aircraft-equipment, and authorization evidence, and a research-only swarm that remains non-dispatchable.

`golden-blocked-cases.json` covers missing operator, stale METAR, airspace conflict, insufficient reserve, expired qualification, invalid maintenance release, missing risk matrix, unsigned policy, armed configuration, autonomous mode, one-to-many staffing, and unacceptable residual risk.

`golden.test.ts` verifies class coverage, IFR evidence gating, named blocker codes where exposed by the pure kernel, non-ready outcomes, evidence-reference arrays, and locale-independent concept IDs.

## Verification

```text
npm test --workspace packages/safety-kernel -- golden.test.ts --run
```

Result: PASS — build succeeded; 1 test file, 2 tests passed.

```text
npm test --workspace packages/safety-kernel -- --run
```

Result: PASS — full safety-kernel suite passed.

```text
npm run typecheck --workspace packages/safety-kernel
npm run build --workspace packages/safety-kernel
```

Result: PASS — typecheck and build completed successfully.

## Limitations

The fixtures intentionally consume the existing pure APIs and controlled metadata; they do not infer regulatory authority, replace signed evidence, or claim that a passing predicate is institutional approval.

## Round 1 review fixes

The golden test now retains accepted synthetic evidence for mission evaluations and asserts exact `MISSION_DATA_EXPIRED` plus `metar-stale` evidence for stale METAR. Expired qualification asserts `MISSING_OPERATOR_PER_AIRCRAFT`; autonomous, armed, one-to-many, and research-swarm cases assert their exact exposed kernel blockers. Missing risk matrix and residual-risk mismatch use `evaluateRisk` with exact fail-closed reasons. Airspace conflict, reserve, and maintenance-release are explicitly marked unsupported by the current pure MissionRevision predicates and are tested to fail closed through `REQUIREMENT_SOURCE_REVIEW_PENDING`, with their limitations recorded in the fixture.

The source ID, extraction hash, policy signature, and labels in these tests are synthetic controlled test metadata (`golden-source`, `golden-hash`, `signed-policy`); they are not claims of signed P0 provenance or qualified regulatory approval.

Verification:

```text
npm test --workspace packages/safety-kernel -- golden.test.ts --run
```

Result: PASS — 1 test file, 2 tests.

```text
npm test --workspace packages/safety-kernel -- --run
```

Result: PASS — 11 test files, 109 tests.

```text
npm run typecheck --workspace packages/safety-kernel
npm run build --workspace packages/safety-kernel
```

Result: PASS — typecheck and build completed successfully.
