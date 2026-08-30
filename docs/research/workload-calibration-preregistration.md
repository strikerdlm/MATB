# Preregistration template: MATB workload dose-response calibration

## Objective and status

Determine whether the deterministic engineering presets produce a reproducible,
ordered workload manipulation in humans. Until this protocol is completed, LOW,
MEDIUM, and HIGH are labels for configured task demand, not validated cognitive states.

## Population

Define the intended population, inclusion/exclusion criteria, language, prior MATB or
aviation experience, corrected vision/hearing requirements, target sample size, and
attrition allowance. Derive sample size from the smallest scientifically important
ordered within-person effect and repeated-measures variance; do not select it merely
to obtain statistical significance.

## Activity and timing

Each participant completes standardized instruction, task-specific practice, and a
predefined proficiency criterion before data collection. In each qualified session,
participants perform LOW, MEDIUM, and HIGH blocks using all six orders across
successive participant assignments (`COMPLETE_COUNTERBALANCE_3`). Keep block length,
rest, time of day, hardware, audio level, input devices, and questionnaire timing fixed.
If reliability is studied, repeat the protocol on at least two additional sessions
separated by the preregistered interval.

## Variables

Primary outcomes:

- complete `nasatlx.rtlx_mean_0_100`;
- ISA trajectory;
- SYSMON hit rate and response time;
- communications accuracy/d-prime and response time;
- tracking RMS deviation and percent time in target;
- resource-management mean absolute deviation and percent time in tolerance.

Secondary outcomes include Bedford, recovery times, strategy/task prioritization, and
estimated SYSMON d-prime (explicitly exploratory). Optional physiology must have a
qualified synchronization report and a prespecified processing pipeline.

## Processing and analysis

1. Freeze the protocol, scenario hashes, seeds, metric schema, exclusions, and analysis code.
2. Validate every session manifest and timing-QC artifact before unblinding conditions.
3. Apply completeness and eligibility gates; do not impute missing task opportunities.
4. Model ordered LOW-to-MEDIUM-to-HIGH effects with repeated-measures or mixed models,
   reporting estimates, confidence/credible intervals, individual trajectories, and
   multiplicity treatment.
5. Examine performance-subjective dissociation and speed-accuracy tradeoffs rather
   than requiring every measure to change significantly.
6. Estimate practice slopes, test-retest reliability/ICC where justified, within-person
   variability, and session-by-condition interactions.
7. Publish deviations, exclusions, null findings, and all protocol/manifests needed to reproduce the dose.

## Success criteria

Success is defined before data collection using minimum ordered effects, acceptable
uncertainty, data completeness, and timing-QC thresholds. A merely significant omnibus
test is insufficient. If ordering is not supported, retain demand-parameter labels or
recalibrate scenarios without retroactively redefining outcomes.
