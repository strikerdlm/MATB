# ADR-001: Version scientific metrics and preserve legacy outputs explicitly

**Status:** Accepted
**Date:** 2026-08-30
**Deciders:** MATB maintainers and study investigators

## Context

The v1 converter exposed a field named `raw_tlx` that summed available native
0–10 subscales, and it calculated SYSMON d-prime with an estimated number of
non-signal opportunities. Both were reproducible software calculations, but
neither was suitable as an unqualified confirmatory endpoint. Existing stored
records and downstream code still depend on those fields.

## Decision

Adopt a versioned metrics registry and additive v2 output schema. Corrected
metrics use explicit names, units, required observations, missingness rules,
and confirmatory-eligibility flags. Legacy values remain readable under clearly
deprecated names; they are never silently reinterpreted. Corrected RTLX becomes
the default DEPDF workload source. Observed SYSMON d-prime fails closed unless
both target and non-target opportunities are explicitly logged.

## Options considered

### Replace v1 fields in place

| Dimension | Assessment |
| --- | --- |
| Complexity | Low |
| Scientific clarity | High for new runs |
| Reproducibility | Poor for historical records |
| Compatibility | Breaking |

### Add versioned v2 fields and retain explicit legacy fields

| Dimension | Assessment |
| --- | --- |
| Complexity | Medium |
| Scientific clarity | High |
| Reproducibility | High |
| Compatibility | Additive |

### Leave v1 semantics unchanged

| Dimension | Assessment |
| --- | --- |
| Complexity | Low |
| Scientific clarity | Low |
| Reproducibility | Superficially stable but semantically ambiguous |
| Compatibility | High |

## Trade-off analysis

The additive approach creates temporary schema breadth and requires consumers
to select a metric version. That cost is preferable to either breaking prior
artifacts or silently changing their numerical meaning. A mixed-schema analysis
is rejected unless records are migrated deliberately.

## Consequences

- `rtlx_mean_0_100` requires all six valid subscales; incomplete forms return
  null rather than a partial composite.
- `dprime_observed_v2` requires uniquely identified, closed target and
  non-target opportunities; unavailable evidence returns null.
- `raw_tlx`, `d_prime`, and `dprime_estimated_v1` remain reproducible but are
  exploratory compatibility fields.
- Timing-QC sidecars characterize software clocks only. Physical onset latency
  still requires photodiode/audio-loopback qualification.
- LOW/MEDIUM/HIGH labels remain engineering presets until human calibration.

## Action items

1. Maintain definitions in `matb_integration/metrics_spec.json`.
2. Require a metrics schema version in new manifests and analytical artifacts.
3. Execute the timing-qualification and workload-calibration protocols before
   making physical-timing or workload-validity claims.
