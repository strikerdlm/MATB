# Polar RR, review and ASTRA baseline verification

Verified 2026-10-03. Evidence uses synthetic signals; no participant recordings
or device identifiers are included. Original development began 2026-10-02.

## Scope

- Exact native HRS ticks exported as milliseconds to headerless TXT, single-column
  CSV and a full timing/quality trace. Interruptions create separate segments;
  raw Parquet and its manifest stay unchanged. Finalization attempts export;
  downloads retry derivation without invalidating the original recording.
- Local descriptive HRV metrics, tachogram, Poincare, PSD when eligible and signal
  quality gauge. Unavailable phase comparisons are omitted.
- Experimental ACC respiratory estimation with abstention for short, flat,
  discontinuous, moving or spectrally ambiguous recordings. Human accuracy is
  unknown; no clinical or readiness score is generated.
- Windows BLE thread preparation and connectability fallback; explicit registered
  participant selection; preparation errors preserve selections; existing active
  capture restoration and controller-lease checks are retained.
- Opt-in frozen ASTRA Polar assignments: 5-minute abbreviated PRE (after at least
  5 minutes adaptation), selectable 10-minute manual option, and one companion
  capture per native block. TASK_PRE remains separate from PRE. Exact participant
  and native session matching gates task release. A completed PRE allows native
  preflight in the same idle reserved visit.

## Automated checks

- 97 Python tests passed: physiology parsers/export/review/respiration/transport,
  backend capture API/runtime/standalone, ASTRA deployment and station resources.
- 34 focused frontend tests passed: capture restoration and selection, API
  downloads, review, companion identity gating and study participant integration.
- Frontend TypeScript and focused ESLint checks passed.
- HRV compatibility script compared 8,208 valid packets, all HRS flag combinations
  and all uint16 RR values against pinned HRV sources. See
  [the report](hrv-compatibility.json) for source hashes and known differences.
- Synthetic browser verification loads the finalized review, omits unavailable
  phase output and downloads the headerless TXT. See the adjacent synthetic
  screenshot; it is a UI fixture, not an observed physiological result.

The HRV operational text reader accepts the TXT but rejects a single-column CSV
with a header; the full trace CSV is readable, but acquisition gaps must not be
concatenated for analysis. Physical BLE reliability, sensor identity matching
across five people, human respiratory accuracy and equivalence of downstream
HRV artifact correction are not established by these software checks.

No active research protocol, participant attempt, completion, consent or baseline
result was created by this implementation. Protocol activation remains an
explicit operator action; existing frozen versions are not silently altered.

## Operator and method documentation

- [ASTRA step-by-step baseline and MATB capture](../../physiology/astra-baseline-polar.md)
- [RR format, review methods and HRV comparison](../../physiology/rr-export-and-review.md)
