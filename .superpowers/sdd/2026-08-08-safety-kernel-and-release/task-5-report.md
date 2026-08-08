# Task 5 report — Risk, NASO, freshness, and controlled exceptions

## Delivered

- Added `risk.ts` and public exports for deterministic `evaluateRisk`, `evaluateFreshness`, and `evaluateException` APIs.
- Added explicit `RiskEvaluation`, `FreshnessResult`, `ExceptionResult`, `RiskEvaluationInput`, and revision-bound `ControlledExceptionInput` contracts. Result factories use the existing recursive freeze helper.
- Risk decisions require an approved, signed, currently effective policy, structurally valid probability/severity matrix, an explicit integer `probabilityLevel` selected from that matrix, an exact matrix-derived residual band, an explicit NASO threshold, required duration where configured, and an explicitly delegated acceptance authority. A supplied manifest is validated as a complete approved policy manifest with valid issued/effective timestamps and an optional future expiry; incomplete, blocked, future-effective, or malformed manifests fail closed. Numeric probability is never converted into an implied matrix row. There are no default matrix cells, NASO bands, duration limits, or authorities.
- Freshness evaluates only supplied UTC instants and policy threshold facts. Exact maximum-age boundaries remain current; later critical data are expired. Missing, conflicting, unverified, malformed, unsigned, inactive, or incomplete policy facts fail closed.
- Controlled exceptions require nonblank, matching revision IDs, only explicit expired/missing data or a current snapshot with `DATA_STALE`, a distinct current alternate source (both snapshot and package provenance differ), consequence, mitigation, future validity end, approved safety review, a band in the approved matrix, NASO band, delegated risk authority, and operator acknowledgement. An exception cannot be silently carried to another revision.
- Added targeted risk and freshness/exception test suites, including malformed-policy, UTC-boundary, manifest qualification/effective-window/non-expiry, explicit probability-level, alternate-provenance, matrix-band, policy-state, authority, revision-ID, and required-exception-field cases.

## Verification

- `npm test --workspace @fac-isr/safety-kernel -- risk.test.ts freshness.test.ts --run` — 25 tests passed.
- `npm test --workspace @fac-isr/safety-kernel` — 93 tests passed.
- `npm run typecheck --workspace @fac-isr/safety-kernel` — passed.
- `npm run build --workspace @fac-isr/safety-kernel` — passed.

## Scope and safety notes

The new APIs evaluate risk and evidence facts only; they do not authorize a mission release or supersede the existing hard-blocker and RACAE safety restrictions. All time evaluation is fixed-input UTC parsing with no clock, I/O, network, browser, or database access.
