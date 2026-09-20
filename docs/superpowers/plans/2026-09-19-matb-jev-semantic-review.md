# MATB JEV Semantic Review and Shadow-Research Integration

Implementation specification supplied by the researcher on 19 September 2026.
Baseline: `2d57ef132be3813ec039b3f028920b5abd1be1e9`.

## Binding scope

Optional, default-off retrospective semantic coding of explicitly selected notes
after evidence reconciliation and station admission. Scientific events, metrics,
eligibility, timing, purpose and automation remain authoritative and unchanged.
No physiology, future prediction, live intervention or operational classification.

Provider input is a minimal, locally reviewed payload bound to one immutable
evidence run, annotation version, question pack and provider/model identity.
Authorization binds exact outbound bytes and is rechecked immediately before
delivery. Synthetic sources first; participant transmission requires protocol and
data-processing authorization. Keys remain server-side. Replay never sends.

## Ordered implementation stages

1. Strict immutable contracts and frozen three-question debrief rubric.
2. Versioned annotations, additive inference ledger and deterministic projection.
3. Exact-payload/provider/purpose authorization and review controls.
4. Bounded single-attempt provider adapter and strict response validation.
5. Explicit optional component and existing station-worker admission.
6. Secured annotation, preview, run, review, retry and export endpoints.
7. Bilingual experimental evidence panel and separate blinded labels.
8. Checksummed export and network-free replay CLI.
9. Synthetic fault fixtures and prespecified semantic evaluation protocols.
10. Regression checks, independent review and verification report.

Each stage requires observed failing tests before implementation. A passing
software suite is not human validation or a provider accuracy benchmark.

## Acceptance boundaries

- Component activation, remote mode and current egress authorization all required.
- Queued work remains bound to its original run and payload.
- One station job makes one provider attempt; unknown delivery is never retried
  automatically. Late responses are retained separately from active assessments.
- No external work during visits, acquisition, held runtimes or maintenance.
- No inference writes to evidence metrics, task snapshots or automation engines.
- Export does not alter the existing evidence bundle and contains no credentials.
- Independent reference labels and post-model adjudication are different records.
- Nanosecond values cross the browser boundary as decimal strings.

The full supplied Sections 1–15 remain the governing acceptance specification.
Future causal-time prediction and shadow-policy work require separate gates.

## Verification status

The initial synthetic-only implementation was merged in PR #72. The remaining
software workflow and offline evaluation tooling are completed in the
[20 September follow-up](2026-09-20-jev-review-completion.md); see its
[verification report](../../reports/2026-09-20-jev-review-completion.md).
No authenticated provider smoke test, physical timing measurement, participant
validation or participant-enabled release qualification has been performed.
