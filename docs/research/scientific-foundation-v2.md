# MATB scientific foundation v2

Status: implemented software contract; human and hardware qualification pending.

## Scientific boundary

The MATB platform measures task behavior, perceived workload, and scenario-grounded
situation awareness. Software verification does not establish human workload
calibration, test-retest reliability, cross-implementation equivalence, physical
stimulus-onset timing, diagnosis, fatigue, or aeromedical fitness.

LOW, MEDIUM, and HIGH are deterministic engineering presets until the workload
calibration protocol is completed. Every generated manifest carries
`workload_label_status: engineering_preset_pending_human_calibration`.

## Metrics schema 2.0

The normative registry is `matb_integration/metrics_spec.json`. Converted blocks
carry `metrics_schema_version: "2.0"` and explicit deprecation mappings.

| Construct | Corrected metric | Legacy compatibility | Confirmatory status |
|---|---|---|---|
| Raw TLX | `nasatlx.rtlx_mean_0_100` | `raw_tlx` and `legacy_subscale_sum_0_60` preserve the old sum | Corrected metric only, and only with six valid items |
| Weighted NASA-TLX | `nasatlx.weighted_tlx_0_100` | None | Null unless all 15 pairwise comparisons were collected |
| SYSMON sensitivity | `sysmon.dprime_observed_v2` | `d_prime` and `dprime_estimated_v1` preserve duration-window estimation | Observed metric only, with unique target and non-target opportunities |
| Tracking | `track.rmse_deviation`, `track.percent_time_in_target` | Newly propagated | Eligible when required runtime samples exist |
| Resource management | `resman.mean_absolute_deviation`, `resman.percent_time_in_tolerance` | Newly propagated | Eligible when required target-tank samples exist |

Partial or out-of-range TLX questionnaires retain their item values and legacy sum
but yield no v2 composite. Legacy SYSMON sessions yield no observed d-prime.
Duplicate, malformed, or ambiguous opportunity outcomes invalidate observed d-prime.

## Runtime records and timing

Legacy CSV remains unchanged. Each session additionally produces:

- `*.events.jsonl`: the authoritative ordered runtime envelope with scenario
  time, `perf_counter` clock-domain timestamps, scheduled event time, dispatch
  lateness, provenance, and explicit `scientific_contract_status`. This additive
  envelope is deliberately marked `not_scientific_event_v3` until the published
  `ScientificEventV3`/`TimingObservationV1` contract pair is emitted and
  reconciled end to end;
- `*.lsl_observations.jsonl`: source-event-linked accepted, dropped, or failed
  mirror attempts; LSL is optional and never the sole scientific record;
- `*.timing_qc.json`: update intervals, scenario deltas, long stalls, event
  dispatch lateness, logger latency, LSL push-call latency, runtime metadata, and
  an explicit statement that physical onset is unavailable without hardware.

SYSMON opens and closes uniquely identified target and protocol-defined
non-target opportunities. Generated canonical scenarios schedule the non-target
windows explicitly; the runtime still refuses to infer them from elapsed time.
Observed d-prime is available only when unique lifecycle outcomes, actor identity,
automation state, planned counts, and the session-bound manifest reconcile.

The legacy Research Console pathway ingests CSV plus an optional manifest.
Converter records therefore carry
`scientific_source_status:
legacy_csv_derived_not_reconciled_to_authoritative_event_stream`, and Console
long-format metrics remain confirmatory-ineligible. The additive
[classic evidence pathway](../implementation/classic-evidence-pipeline.md)
ingests newly emitted ScientificEventV3/TimingObservationV1 captures, reconciles
their source IDs and exposes metric-level eligibility separately. It does not
relabel old runtime envelopes or upgrade historical CSV derivatives.

## Analysis migration

The v2 confirmatory family is `sysmon_hit_rate`,
`nasatlx_rtlx_mean_0_100`, and `bedford`. Estimated SYSMON d-prime and summed TLX
remain available as exploratory legacy series. Statistical inputs containing more
than one `metrics_schema_version` are rejected until an explicit migration is
performed. Schema/version/eligibility metadata contributes to analysis fingerprints.

Historical reprocessing must reproduce all legacy values exactly. A corrected field
is allowed to be null when the historical log did not capture its required evidence.

## Advancement gates

The experimental adaptive-automation component now separates allocation policy,
quality, and failure realization and records handoff audit links. Participant-facing
runtime integration, trust claims, closed-loop workload intervention, and
EEG/ERP-grade synchronization remain downstream work. The optional LSL mirror is
implemented, but streaming support alone is not timing qualification. Promotion
may occur only after:

1. converter/runtime regression tests pass;
2. the timing qualification protocol has a signed hardware report for the intended rig;
3. LOW/MEDIUM/HIGH calibration is completed or the labels remain explicitly provisional;
4. confirmatory analyses use only complete, versioned, eligible metrics.
