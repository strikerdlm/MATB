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

- `*.events.jsonl`: ordered schema-versioned records with scenario time,
  `perf_counter` clock-domain timestamps, scheduled event time, dispatch lateness,
  and LSL clock time when streamed;
- `*.timing_qc.json`: update intervals, scenario deltas, long stalls, event
  dispatch lateness, logger latency, LSL push-call latency, runtime metadata, and
  an explicit statement that physical onset is unavailable without hardware.

SYSMON opens and closes uniquely identified target opportunities. The current
continuous-monitoring runtime does not invent non-target windows; observed d-prime
therefore remains unavailable until a study protocol explicitly defines and logs
non-target opportunities. Direct hits, misses, false alarms, response time, and hit
rate remain usable.

## Analysis migration

The v2 confirmatory family is `sysmon_hit_rate`,
`nasatlx_rtlx_mean_0_100`, and `bedford`. Estimated SYSMON d-prime and summed TLX
remain available as exploratory legacy series. Statistical inputs containing more
than one `metrics_schema_version` are rejected until an explicit migration is
performed. Schema/version/eligibility metadata contributes to analysis fingerprints.

Historical reprocessing must reproduce all legacy values exactly. A corrected field
is allowed to be null when the historical log did not capture its required evidence.

## Advancement gates

Adaptive automation, trust experiments, workload-triggered handoffs, and claims of
EEG/ERP-grade synchronization remain downstream work. They may begin only after:

1. converter/runtime regression tests pass;
2. the timing qualification protocol has a signed hardware report for the intended rig;
3. LOW/MEDIUM/HIGH calibration is completed or the labels remain explicitly provisional;
4. confirmatory analyses use only complete, versioned, eligible metrics.
