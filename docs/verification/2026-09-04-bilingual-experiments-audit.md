# Bilingual experiments and calculation audit

Date: 2026-09-04. Scope: implementation and local validation in the MATB repository; delivery is through the associated pull request. No deployment was performed.

Delivery integration: incorporated main revision `109df94`, preserving its versioned OpenMATB appearance profiles alongside bilingual instructions and practice isolation. Post-integration validation passed 124 frontend tests, 36 focused backend tests, lint, production build/type checking, and the browser regression for language changes preserving visit, display, and appearance profile. The loading comparison and screenshots below describe the implementation before that upstream appearance-profile integration.

## Participant experience delivered

`/start` now presents all six experiment families. Each has Spanish and English explanations of the measurement, activity, duration, equipment, practice, and result interpretation. The existing dark visual identity is retained. Selection leads to preparation and instructions, with practice selected by default. Study mode preserves assigned protocol requirements.

| Experiment | Participant route | Execution and requirements |
| --- | --- | --- |
| OpenMATB multitasking | `/openmatb/setup` | Native station readiness, language-specific instructions, participant code and visit; practice runs the practice block |
| Synthetic small unmanned aircraft systems (sUAS) | `/mission/setup`, `/mission/test` | Study protocol with prior valid PVT; separate existing technical simulation for exploration |
| Liftoff simulated flight | `/liftoff/setup` | Simulator telemetry, assigned study context and task order; explicit performance-only reason when physiology is unavailable |
| Cognitive battery | `/screen` | Simple reaction time, choice reaction time, 2-back working memory, mouse tracking |
| Psychomotor Vigilance Task / Karolinska Sleepiness Scale | `/pvt` | KSS followed by instructions and PVT; study PVT requires complete ten-minute timing evidence |
| Polar H10 physiology | `/physiology/polar-h10` | Device connection and signal acquisition; optional for unrelated experiment journeys |

The sidebar follows the selected activity. On mobile it collapses into an experiment menu. Researcher navigation retains scenario design, protocol information, participant assignment, equipment configuration, and family-specific analyses. Liftoff now has a dedicated analysis page at `/analysis/liftoff`.

The catalog comes from the read-only `/experiments/catalog` endpoint. Optional components remain visible; disabled components and missing readiness requirements produce an explanation and next action. Readiness is checked again at launch. Catalog discovery uses component manifests without importing unavailable optional runtimes.

Language changes preserve preparation choices. OpenMATB uses `matb-fac-en@1.0.0` for English instructions and maps native launch to `en_EN`; Spanish maps to `es_CO`. Session metadata and questionnaires use the selected instruction language. Existing audio assets remain intact. The existing qualified English COMM stimulus bank is retained; selecting Spanish explanatory instructions does not translate that experimental stimulus bank.

## Findings and corrections

| Finding | Correction and evidence |
| --- | --- |
| Cognitive input could accept nonfinite/negative reaction times, malformed samples, or inconsistent responses | Strict validation; recorded sides and letters support derivation of choice and 2-back correctness; chronology is checked. Reproduced in new scoring regressions. |
| Tracking validity depended on a presumed 60-Hz screen | Version 2 uses elapsed coverage and a time-weighted squared-error integral, excluding gaps above 250 ms. Equivalent constant-error examples pass at 30, 60, and 120 Hz. |
| PVT duration alone could imply protocol completion despite inconsistent or incomplete events | Versioned timing evidence includes actual elapsed time, ordered trial events, interruptions, maximum frame gap, and terminal phase. Invalid chronology is rejected; short or interrupted recordings can be saved but cannot satisfy a study prerequisite. |
| Visit state could imply completion without valid assessment evidence | Journey completion is derived from saved study assessments, required blocks, and questionnaires for the selected family. Legacy PVT evidence is not promoted to current timing validity. |
| Practice could share study assessment or analysis paths | Persisted purpose, separate cognitive/PVT practice storage, study-only eligibility filters, and direct API export guards. Technical simulation retains its existing classification. |
| OpenMATB language changes could reset preparation or launch the wrong language | Preserve setup state, add English instruction protocol, and use protocol locale consistently through native launch and saved session metadata. |
| Liftoff debrief submitted fixed KSS and workload values | Removed automatic ratings. Participants must answer KSS and all six workload questions. The frontend regression failed before the correction and now passes. |
| Workload scales were presented inconsistently | Complete unweighted RTLX is explicitly reported on 0–100. sUAS retains its historical 0–60 sum under a legacy label. Incomplete questionnaires cannot produce a complete normalized result. |
| sUAS session-level metrics were copied into each block | Persist metrics derived from each block's effective records; checkpoint rollback records are excluded. Calculation identity is `suas-debrief-v2`. |
| Invalid Liftoff lap values could propagate or be silently dropped | Reject nonfinite/nonpositive or malformed lap entries. Missing observations remain explicit. Partial submission state supports retry without resending already saved responses. |
| Missing-session bundle requests could become server errors after export guards | Use the existing managed error translation for session lookup. Direct API tests confirm practice denial and 404 for nonexistent sessions. |
| Header always claimed a live connection | Display checking, connected, or offline based on actual backend requests, with bounded polling and request cancellation. |

Results provide units, missing-data explanations, and interpretation limits; detailed statistical output remains expandable. Different experiment families are not combined into a new score. The registered statistical specification, repeated-measures structure, eligibility rules, multiplicity correction, and convergence checks are retained.

## Calculation references and independent examples

The PVT boundary tests preserve the existing protocol: false starts below 100 ms, responses from 100 ms to below 500 ms, and lapses at or above 500 ms. Explicit examples test 99.999, 100, 499.999, and 500 ms. A complete synthetic record of 272 responses at 200 ms gives median reaction time 200 ms and mean reciprocal response speed 5 per second. Timing tests also cover out-of-session events, mismatched false-start timestamps, terminal continuity, shortened duration, interruptions, and the exact 250-ms frame-gap boundary. See [published PVT methodology](https://pmc.ncbi.nlm.nih.gov/articles/PMC3079937/).

Unweighted RTLX is the arithmetic mean of all six ratings expressed on 0–100. For native sUAS values 1, 2, 3, 4, 5, and 9 on 0–10, the historical sum is 24/60 and normalized RTLX is 40/100. A missing subscale produces no complete normalized score. These outputs are explicitly distinguished from pairwise-weighted NASA-TLX. See [NASA's methodology review](https://humansystems.arc.nasa.gov/groups/TLX/downloads/HFES_2006_Paper.pdf).

Additional reference checks include:

- Cognitive tracking offset (30, 40) pixels has distance 50 pixels; with amplitude 100 pixels, normalized RMS error is 0.5 at 30, 60, and 120 Hz.
- Detection sensitivity tests cover known normal-quantile examples, equal hit/false-alarm rates, and missing signal/noise denominators. Existing converter tests retain separate observed-event validity and legacy estimates.
- Liftoff valid laps 61.2, 63.0, and 60.8 seconds give median 61.2, best 60.8, and completion proportion 3/4 when one lap is invalid. Zero completed laps, irregular sampling, unvalidated coordinates, and absent reference paths remain explicit missing results.
- RR intervals 1000, 1100, and 900 ms give sample SDNN 100 ms and RMSSD `sqrt((100² + 200²)/2)` = approximately 158.114 ms. A rejected 2500-ms interval between two groups of ten 1000-ms intervals remains in the raw observations, leaves 20 accepted intervals and 18 adjacent usable pairs, and is never bridged. Zero RMSSD has no logarithm or fabricated spectral ratio.
- Existing resource-management, tracking, sUAS research-debrief, and questionnaire tests verify component metrics, missingness, lifecycle reconciliation, and invalid observations. HRV contact, continuity, duration, spectral availability, and quality gates remain conservative and unchanged.

These checks establish software behavior for the tested examples. Browser-reported timing evidence is not an independent physical timing measurement.

## Historical data and migrations

The execution-purpose migration is additive and repeatable. Tests cover both existing visit schedules: days 0/8/15 and 0/3/6/9/12/15. Stored dates and protocol definitions remain unchanged.

Corrected cognitive calculations use screen version 2; current cohort calculations exclude prior scoring versions and practice. PVT evidence uses version 2. Existing raw observations and historical artifacts are retained. Explicit assessment overwrites are archived. Human capability factor (HCF) metadata changes are archived before refresh so a changed eligibility set cannot silently leave an old practice-derived fit active. Historical fast-mode records are identified using their recorded mode evidence; unspecified historical runs are not guessed to be practice.

Historical Liftoff sessions collected through the former fixed-rating form need researcher review before scientific use of those questionnaire values. The implementation cannot reconstruct answers that were never collected and does not silently replace them. Historical 0–60 workload sums retain their original meaning.

## Validation performed

Counts below describe separate runs and overlap; they must not be added into one unique-test count.

| Check | Observed result |
| --- | --- |
| Initial investigation baseline | 119 frontend and 123 backend/calculation tests passed |
| Full backend suite after main implementation | 243 passed, 1 skipped; the skip is a POSIX-specific process probe on Windows |
| Full frontend unit suite | 119 passed across 33 files |
| Broad core calculation run | 254 passed; one contract-schema mismatch found and corrected |
| Subsequent calculation/schema run | 91 passed, 5 skipped; all corrected Polar contract checks passed. The five skips require an absent historical smoke CSV. |
| Final sUAS runtime/failure checks after rollback-record adjustment | 11 passed |
| Final Liftoff/Polar API export checks | 7 passed |
| Additional HRV and Liftoff practice-eligibility checks | 13 passed |
| Dedicated Liftoff statistical model checks | 3 passed |
| Final browser workflows | 11 passed |
| Type checking, lint, production build | Passed |
| Diff whitespace check | Passed |

The browser run covers all six catalog selections in Spanish and English at 1440 and 390 pixels, unavailable components, selection focus, no horizontal overflow, language-state preservation, all four cognitive practice tasks, KSS/PVT practice, and the simulated Liftoff workflow with manually entered ratings. Axe found no serious or critical violations on the catalog states tested. Backend suites cover launch failure, recovery/reconnect behavior, duplicate assessment submissions, invalid timing, missing data, practice isolation, study prerequisites, and migrations. Test databases and simulation artifacts were isolated from participant data.

Windows test-server teardown required stopping the exact Node and Python processes created by the browser run; all 11 tests had passed before teardown. The launcher was first invoked with an incorrect Python environment variable, then corrected to the repository-supported `MATB_PYTHON`. Neither issue changed test assertions or application behavior. Nonfatal warnings included a dependency deprecation and unwritable pytest cache folders.

## Loading and accessibility

A clean copy of the prior tracked frontend was built with the same installed dependencies. Comparing the initial `/start` HTML script assets:

| Measurement | Before | After |
| --- | ---: | ---: |
| Initial script requests | 10 | 9 |
| JavaScript bytes, uncompressed | 635,651 | 631,870 |
| JavaScript bytes, locally gzipped | 197,181 | 196,883 |

The size reduction is modest: approximately 0.6% uncompressed and 0.15% gzipped. These are asset measurements, not a claim of a perceptible loading-time improvement. The fresh catalog makes one backend catalog request and no experiment-specific readiness request until selection. Capability/protocol reads are shared; detailed readiness is deferred. Task runners, charts, and maps remain outside the catalog import path; inspection of its emitted initial scripts found no corresponding module markers.

The interface adds focus movement after selection, keyboard-operable controls, readable labels, reduced-motion behavior, actionable errors, and explicit save confirmation. Mobile navigation was visually reviewed and collapsed to leave the experiment content closer to the top.

Evidence assets: [loading measurements](experiments-2026-09-04/loading.json), [desktop catalog](experiments-2026-09-04/catalog-desktop.png), [mobile catalog](experiments-2026-09-04/catalog-mobile.png).

## Remaining validation limits

Physical Polar H10 acquisition, actual Liftoff hardware/control timing, native OpenMATB windows on the intended monitor, and audio playback were not exercised in this run. Simulated transport and process tests do not qualify those station behaviors. Full real-duration study execution of every family in both languages therefore remains a station acceptance task. The tested browser accessibility states are not an exhaustive accessibility certification.

The existing scientific measures retain their research interpretation. Completion and software conformance do not establish clinical, aeromedical, operational, or hardware timing validity.
