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
