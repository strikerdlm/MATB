# Task 3 implementation report — frozen study/analysis registry

Base: `1871e899d93086eb45523e8e207f1e8687c67ab4`. Worktree: `/root/repos/MATB/.worktrees/repeatable-study`, branch `codex/repeatable-study`. Only Task3 changes; no push/merge. Implementation commit and final verification are recorded below; this report is committed separately.

## Delivered behavior

A researcher can author constrained longitudinal, pre/post/recovery or repeated-block drafts in English or Spanish, edit scheduled visits and occasions, choose installed instrument bindings and frozen participant language, author recovery intervals, preparation criteria, repeat/interruption policy, outcomes/contrasts, eligibility and HCF policy, validate, rehearse, attest/freeze, and explicitly activate collection. Templates are synthetic, required scientific choices have no approved defaults, and synthetic status prevents freeze. Version inspection, clone/amendment, activation, explicit participant/visit/arm assignment and future-assignment amendment are exposed in `/study` and `/study/assignments`. There is no JSON-only authoring requirement; exact JSON remains a diagnostic version disclosure.

Approval is bound to the current canonical draft fingerprint and a successful isolated rehearsal of that exact draft. Editing invalidates the rehearsal identity. Rehearsal actually calls occasion materialization and shared attempt creation/start/finish in an ephemeral SQLite database, using practice lifecycle records there; only the rehearsal receipt is retained in the real workspace. It produces no participant competence, physical qualification or study outcome evidence. Freeze allocates two UUIDs first, cross-references stable IDs, and then independently hashes StudySpecV1 and AnalysisPlanV1; there is no recursive hash pair.

Assignments are server-owned immutable relations from participant/visit/arm/version to materialized occasion UUIDs. Public local occasion metadata or an arbitrary frozen version_ref grants no assignment authority. Only the explicitly active version can receive new assignments. Activating another version does not repin existing visits. Explicit amendments name the prior unstarted assignments, create replacement occasions and preserve the old relation plus actor/reason/full before-after diff. Any actually started assigned visit remains pinned; a stale created attempt cannot start or save after amendment. SQLite write locking serializes activation/assignment/amendment/start decisions. Existing deployment protocol/schedule mismatch checks remain, with an additional workspace study identity/template-family binding. Newly enrolled participants receive the active authored visit schedule; existing visit schedules must match the version selected for assignment/amendment.

Every new study acquisition resolves participant, visit, current purpose, assigned occasion and frozen configuration on the server. PVT/screen saves, native preparation/start/resume/ratings, H10 preparation/start, Liftoff preparation/transitions and mission preparation/start/resume use the selected shared attempt. Required preparation fails closed with an explicit pending-engine error. Standalone practice and historical read-only access remain supported. Browser admission remains awaited before KSS/stimulus timing. Frozen language drives PVT/screen runners, native participant ratings and optional setup payloads without rewriting the researcher's language preference. Accelerated browser URLs retain Task1's practice behavior.

Native assigned capture runs exactly one prescribed condition per suite, with no injected old PRACTICE block. Independent repeated HIGH occasions retain independent suites, scenario maps, directories, native block instances, rating sidecars, scores and shared source links. New maps/sidecars/scores use the assigned occasion UUID; labels remain the actual condition. The legacy visit/workload-cell projection is explicitly `inapplicable_assigned_occasion`; it is not a failed authoritative save and existing imported cells are untouched. Native task/rating/evidence links resolve to the exact shared task and exact-target questionnaire, rather than creating legacy_compat children. Actual completion and interruption/restart update those same shared attempts. Pending ratings for an interrupted native task are interrupted with unknown cause and a repeated task gets a distinct target. Existing legacy paths/bytes remain readable.

Selected prerequisite attempts are immutable records. PVT qualification uses `require_study_pvt(..., attempt_id=...)` in actual mission preparation. Native/Liftoff use `require_task_order(..., source_session_id=...)` for prescribed predecessors. An explicit source must satisfy participant/visit/current-purpose/source completion checks, independent of legacy task_sequence. Unrelated LOW/MEDIUM/HIGH cells cannot satisfy it. Conversely the old participant task_sequence cannot add a prerequisite omitted by the frozen assignment. Recovery records have an exact finished anchor attempt, actual administrative start/end, elapsed-duration enforcement and separate start/finish attestations.

## Exact downstream contracts

### StudySpecV1 / AnalysisPlanV1

`app.study_registry_schemas` exports `StudySpecV1`, `AnalysisPlanV1`, `DraftPayload`, `OccasionSpec`, `RecoverySpec`, and strict request models. All reject unknown fields. Drafts may leave typed policy groups null, but validation/rehearsal/freeze reject those omissions. Textual `study.rules` and `analysis.rules` remain required explanatory rationale; engines must use the typed policy fields rather than interpret prose.

StudySpecV1 includes `version_id`, `analysis_plan_id`, `study_id`, `title`, `template_family`, `synthetic`, `enabled_instruments`, `implementation_sha256`, `visits[{ordinal,code,scheduled_day}]`, `arms`, `assignment_method='explicit_researcher_selection'`, `occasions`, `recovery_intervals`, `rules`, `preparation_policy`, `repeat_policy`, `interruption_policy`.

Each occasion has `key`, `visit_ordinal`, `instrument`, `phase`, `order`, `condition_by_arm`, `locale` (`en`/`es-419`), `config`, `prerequisite_keys`, `target_key`, `collection_group`, `accompanying_key`. Keys and within-visit order are unique; prerequisites are earlier in the same visit; native questionnaires follow their exact native target in the same language. H10 accompaniment must name an earlier native/Liftoff/mission occasion in the same explicit collection group. Recovery entries are `{key, anchor_key, before_key, duration_seconds}`; duration is researcher-authored and positive, with earlier anchor/later target in one visit.

`app.study_policies` contains the bounded typed contracts:

- `PreparationRequirement`: `occasion_key` (resolves the exact instrument/configuration in this immutable version), `placement` (`before_baseline`/`prescribed_later`), affirmative `demonstration_required` and `acknowledgement_required`, `comprehension[]`, `practice[]`, `rationale`.
- Each `Criterion`: `id`, `rationale`, supported `metric`, `comparator` (`gte`/`lte`/`eq`), finite researcher-entered `threshold`. Comprehension supports `comprehension.correct_fraction` with threshold 0..1. Practice allowlist: PVT `pvt.median_rt_ms`/`pvt.lapses`; screen `screen.simple_rt`; native `sysmon.hit_rate`/`track.rmse_deviation`. Other practice metrics reject validation; no arbitrary expression evaluator or default pass value exists.
- `RepeatPolicy`: `permitted_causes`, integer `max_attempts>=1`, `selection` (`explicit`/`first_finished`/`latest_finished`), `rationale`. Repeat creation enforces cause and limit now. Cause is `intentional_repeat` for a finished predecessor, or its recorded interruption category. The supported categories preserve Task2: withdrawal, operator_stop, hardware_failure, software_failure, planned_interruption, unknown, participant_stop, technical_failure, lost_connection, other.
- `InterruptionPolicy`: `available_outcomes` (`retain_available`/`exclude_attempt`) and rationale; actual categories remain separately recorded without reinterpretation. Outcome eligibility is a Task5 responsibility.
- Analysis `eligibility_policy`: `repeat_selection`, `incomplete_denominator` (`assigned`/`started`/`finished`), `missing_handling` (`exclude_outcome`/`complete_case`), independent `source_requirement` (`complete_verified`/`report_status`), `physical_requirement` (`qualified`/`report_status`), `human_calibration_requirement` (`calibrated`/`report_status`), `participant_preparation_requirement` (`prepared`/`report_status`), and `protocol_requirement` (`valid`/`report_status`). `configuration_pooling` is `identical_only` or `explicit_review`; the latter requires `pooling_review`, a researcher rationale/reference, never a claim of psychometric or perceptual equivalence. `hcf_enabled`, `hcf_screen_keys`, `hcf_attempt_selection` prescribe designated screen occasions and exactly one eligible attempt per participant. `rationale` is required. Historical unknown handling remains `exclude` or `reviewed_classification_required`, and reviewed classification alone is not plan permission.

AnalysisPlanV1 additionally includes `version_id`, `study_version_id`, unit (`participant`/`visit`/`attempt`), outcomes `{key,metric,occasion_keys,summary}` and contrasts `{key,left_outcome,right_outcome,operation:'difference'}`. Allowed summaries: individual/mean/median. Outcome identifiers: pvt.median_rt_ms, pvt.lapses, pvt.kss; screen.hcf, screen.simple_rt; openmatb.workload, openmatb.performance; physiology.raw, physiology.mean_hr_bpm; liftoff.performance; suas.performance. Validation checks instrument/reference compatibility; this task does not claim these descriptive derivations have been executed.

### Bindings and packaging handoff (Tasks4/5/7)

`app.study_bindings.binding_options(db)` only offers active optional components and checks actual dependency availability. Core returns PVT/screen without importing absent sUAS implementation merely because its schema module exists. Liftoff/H10/native cannot validate when their component is disabled. H10 authoring validates supported CaptureSettings independently of a live BLE connection; actual selected-device stream settings are checked during capture creation. Station hardware readiness/qualification remains separate.

Supported executable configuration identities:

- PVT/screen: exact installed browser config `{binding_id:'pvt-browser-v1'|'screen-browser-v1',sha256,input_mapping:'space'|'screen-default',scoring:'pvt-current'|'screen-current',fast_mode:false}`.
- Native: exact published `preset`, `instructions`, `visual` objects `{id,version,sha256}` plus `input_mapping:'openmatb-default'`, `scenario_generator:'published-preset-v1'`, `scoring:'openmatb-current'`; native conditions LOW/MEDIUM/HIGH and instruction language must match.
- Questionnaire: `MATB-FAC-WORKLOAD-1.0`, browser-ratings, rtlx-mean-bedford; separately executable workload questionnaires only target an assigned OpenMATB task. A PVT-target standalone workload binding rejects. PVT KSS and embedded mission/Liftoff ratings remain in their original contracts.
- H10: polar-h10-pmd-v1, rr-ecg-acc, exact full CaptureSettings, raw-streams. This covers the implemented streaming mode, not unimplemented sensor modes.
- Liftoff: liftoff-telemetry-all-v1 input/binding, exact full LiftoffConfiguration, liftoff-current.
- Mission: suas-protocol-v1, installed configured scenario `{id,sha256}`, exact validated PresentationConfig or null standard 2D, suas-default, suas-current, `practice_included:true`; each arm is a LOW/MEDIUM/HIGH permutation. A study PVT prerequisite is mandatory. Scenario options resolve the configured `MATB_SIMULATION_SCENARIO_DIR`; authored presentation validation uses the same pure binding implementation as launch. No live-traffic research binding is approved. Constrained authoring offers the standard 2D mission binding; existing advanced presentation payloads remain validated/readable via their exact API contract and version disclosure.

`implementation_sha256` is server-resolved during draft create/update and included in the draft attestation hash and frozen StudySpec. Validation refuses changed installed implementations until the researcher saves/reviews/rehearses the new hash. Launch rechecks both semantic binding availability and the frozen implementation hash. Historical reads do not require the installed implementation to still match. Packaging must preserve exact file bytes and these inventories:

- Browser: component subtree (`src/components/pvt` or `screen`, .py/.ts/.tsx excluding .test.), instrument frontend pure library and page, shared `src/lib/i18n.tsx`, `components/instructions/InstructionAudio.tsx`, backend instrument router (PVT scoring lives there), Python instrument scoring subtree, actual matching instruction MP3 files (PVT includes KSS). Screen additionally includes `matb_integration/log_converter.py` (`_d_prime`) and `matb_integration/suhir/hcf.py`.
- Native: openmatb source subtree; scenario_builder.py, openmatb_visual_profiles.py, log_converter.py, metrics_schema.py, metrics_spec.json; backend openmatb_runtime.py.
- Questionnaire: WorkloadQuestionnaire.tsx, shared i18n.tsx, backend openmatb_runtime.py.
- H10: matb_integration/physiology; backend physiology_runtime.py and physiology_schemas.py.
- Liftoff: matb_integration/liftoff; backend liftoff_runtime.py and liftoff_schemas.py.
- Mission: matb_integration/suas, frontend components/mission and lib/simulation, backend simulation_runtime.py.

Optional implementation directory inventories include .py/.json/.ts/.tsx and exclude .test. files. Each digest sorts by the case-sensitive logical POSIX relative path string, hashes that UTF-8 path, a NUL separator and the unchanged file bytes. Both path serialization and sorting are platform-independent; file bytes are deliberately not normalized. Installed source changes require a compatible preserved package or an explicitly reviewed new version, rather than silently changing a pinned assignment's stimulus/scoring identity.

### Persistence and APIs

New tables in `app.study_registry_models`: study_workspace (singleton additive identity/deployment binding); study_draft; study_version (primary StudySpec UUID and unique independent AnalysisPlan UUID plus canonical JSON/hashes and attestation); study_rehearsal; study_activation (append-only monotonic activation event); study_assignment; study_amendment; study_attempt_selection; study_recovery_interval; study_registry_lock. Immutable SQL triggers protect frozen drafts, versions, rehearsals, activations, assignment relations, amendments and selections. Recovery identity/start attestation is immutable; the one administrative completion writes end time/actor/reason, then becomes immutable. Existing source/attempt/purpose ledgers remain authoritative for original data.

Router prefix `/study`:

- GET templates/{longitudinal|pre-post-recovery|repeated-block}, bindings, drafts, drafts/{id}, versions, versions/{id}.
- POST drafts; PUT drafts/{id}; POST drafts/{id}/validate, /rehearse, /freeze (`actor,reason,sha256,rehearsal_id`).
- POST versions/{id}/clone; /activate (`actor,reason`); /assign (`participant_id,visit_id,arm,actor`); /amend (`assignment_ids,actor,reason`).
- GET assignments (optional participant_id), assignments/{id}; detail includes version, exact occasion map, attempts, current/started, amendment events and administrative recovery records.
- POST attempts/{id}/prerequisites (`selections:{occasion_key:attempt_uuid}`), immutable after first selection; actual attempt admission requires exactly every prescribed key and a finished currently study predecessor.
- POST assignments/{id}/recovery/{key}/start?anchor_attempt_id={id}, /finish, both named actor/reason bodies. One interval record per assignment/key preserves its selected anchor and actual admin times; no undocumented reset or substitution.

Existing `/assessments` create/repeat/start/save flows remain, with additive `assignment_context` in attempt views. That context supplies assignment/version/analysis IDs, both canonical hashes, implementation_sha256, participant/visit/arm, occasion key/UUID and exact configuration/language, preparation/repeat/interruption policies, recovery declarations and honest `preparation_gate`, `resource_gate`, `analysis_gate` = `not_implemented` hooks. Preparation requirements are scoped to the assigned visit.

Services for downstream consumption: `study_registry.get_version/version_view`, `active_version`, `assignment_is_current`, `assignment_started`, `assign/amend`; `study_admission.for_occasion`, `resolve_assignment`, `select_prerequisites`, `require_prerequisites`, `guard_source`, `sync_runtime_attempt`. Use server relation resolution, never trust client version metadata.

Errors: 409 `study_assignment_required` (actionable `/study/assignments` URL), `study_binding_unavailable`, `study_preparation_engine_pending`, `study_repeat_not_permitted`; validation/rehearsal issues are 422 `study_validation_failed` with path/message entries. Stale rehearsal/freeze and changed prerequisite selection are 409. Task4 must replace `study_policies.require_preparation` with actual measured evidence evaluation; required demo/ack/comprehension/practice presently cannot pass. Task5 must execute eligibility/HCF/descriptive plans into immutable derivations. Task6 must implement the resource coordinator/live visit protection. None is implied by synthetic rehearsal or a frozen approval record.

## Test/fixture integrity and self-review

Existing prospective study fixtures were migrated through actual draft → validation/rehearsal → named freeze → activation → assignment → shared attempt admission. No admission function is monkeypatched for backend public acquisition tests. `tests/study_policy_fixtures.py` and browser `e2e/study-fixtures.ts` affirmatively prescribe no preparation requirements, with an explicit isolated transport/lifecycle-only rationale; this does not invent or approve participant competence. Required-preparation and unsupported-metric regressions independently verify fail-closed behavior.

Generic non-native questionnaire target/lifecycle tests are explicitly isolated model/service practice fixtures, because the generic relationship model is broader than the executable native questionnaire adapter. Historical unknown-screen and recovery fixtures seed genuine legacy records directly. The historical HCF refresh regression seeds legacy screens and invokes the unchanged refresh service/mathematics; new assigned screens do not trigger unplanned global fit mutation. Controller explicitly approved this distinction; Task5 will replace exploratory mutation with immutable plan derivation.

Full source core runs intentionally skip assigned native/H10/Liftoff integrations when those components are disabled, but continue shared PVT/screen/registry/admission coverage. The core catalog regression disables every optional component and asserts only PVT/screen are offered. Auto executes the optional integrations. Controller will additionally run the prepared physically stripped-core startup/catalog check on the committed snapshot; that packaging result is not claimed here.

Self-review found and fixed: stale amendment admission; server-owned relation spoofing; exact-target questionnaire enforcement; native repeated-label sidecar/result collisions; evidence source inheritance; actual optional lifecycle completion/restart; orphaned pending native ratings on interrupted repeat; explicit prerequisite bypass via legacy workload cells; legacy task_sequence adding unplanned prerequisites; disabled-component authoring/catalog leakage; cross-platform digest path/order; shared instruction and server scoring fingerprint omissions; source change admission; recovery end attestation; invalid accompaniment topology; URL-assignment selection being reset when visit data arrives. The browser regression also confirmed that `fast=1` remains practice by Task1 design; the real study-language test uses normal assigned study entry.

Known scope limits: no measured preparation engine, analysis execution/HCF engine or resource coordinator; no physical sensor/native hardware qualification; no remote authentication or automatic inventory. Mission form authoring currently offers standard 2D, while advanced installed presentations remain supported through the strict existing API/clone disclosure. Rehearsal exercises shared assignment/lifecycle services, not real stimulus timing, sensor hardware or scientific pass criteria. Historical sources never become approved assignments by association. Existing source raw bytes/scoring formulas are preserved; scenario/runtime adaptation only changes assigned instance routing/order and admission.

## Verification evidence

Backend commands ran from `webui/backend`, using this exact prefix (auto unless explicitly core):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/matb-predictability-testdeps PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 MATB_COMPONENTS=auto /root/repos/MATB/.venv/bin/python -B -m pytest -q -p no:cacheprovider -p anyio.pytest_plugin
```

Threaded/async backend and browser tests used escalated execution as required by the environment; sandbox threadpool runs can hang. Logs are retained under `/tmp`.

Meaningful RED → GREEN records (not every interim fixture failure is claimed as product TDD):

- `tests/test_study_registry.py`: initial RED 4 failed (registry absent), `/tmp/task3-registry-red.log`; initial GREEN 4 passed, `/tmp/task3-registry-green.log`.
- Actual H10 completion: `/tmp/task3-h10-red-escalated.log` failed because the shared attempt remained started after capture lifecycle complete; `/tmp/task3-h10-green.log` passed after syncing actual completion.
- Recovery/semantic additions: `/tmp/task3-recovery-red.log` had two real missing behaviors (end attestation, impossible accompaniment accepted), plus one corrected invalid participant fixture; subsequent policy/recovery gates passed.
- Disabled optional binding catalog: core `tests/test_study_registry.py -k binding_catalog`, `/tmp/task3-bindings-core-red.log`, 1 failed; core registry later passed with capability-gated options.
- Repeat limit: core `tests/test_study_registry.py`, `/tmp/task3-policy-red.log`: 1 failed/9 passed; `/tmp/task3-policy-green.log` (registry/acquisition/HCF subset): 16 passed.
- Native interrupted repeat: `tests/test_study_acquisition.py -k interrupted_repeat`, `/tmp/task3-native-repeat-red.log`: 1 failed (target questionnaire remained created); `/tmp/task3-native-repeat-green.log`: 4 passed across native/H10 cases.
- Changed installed browser binding: core `tests/test_study_registry.py -k changed_installed`, `/tmp/task3-binding-change-red.log`: 1 failed (start accepted); later core/auto covering gates include its passing rejection.
- Actual frozen task predecessor: `tests/test_study_acquisition.py -k liftoff_launch`, `/tmp/task3-task-order-red.log`: invalid selected source incorrectly returned 201; a second test initially had an isolated fixture DB setup error. Corrected fixture plus actual source enforcement: `tests/test_study_acquisition.py tests/test_experiment_safety.py`, `/tmp/task3-task-order-green.log`: 21 passed.
- Frontend constrained authoring initial RED missing component, then GREEN; final authoring hash/edit/rehearsal test: `npm test -- src/components/study/StudyEditor.test.tsx`, `/tmp/task3-front-authoring.log`: 2 passed.
- URL assignment/visit race: `npm test -- src/components/assessments/AssessmentPicker.test.tsx`, `/tmp/task3-picker-url-red.log`: 1 failed/8 passed. After ordering context reset before assignment selection, `npm test -- src/components/assessments/AssessmentPicker.test.tsx src/components/assessments/AssessmentPages.test.tsx src/components/study/StudyEditor.test.tsx`, `/tmp/task3-picker-url-green.log`: 15 passed.

Covering evidence before the final small closure fixes:

- Full auto backend prefix with no test arguments: `/tmp/task3-backend-full-second.log`: **401 passed, 1 skipped, 9 warnings**. Initial full run was 389 passed/5 failed/1 skipped; all five were resolved without bypassing study admission.
- CI core profile (same prefix with MATB_COMPONENTS=core and the workflow's optional test-file ignores): `/tmp/task3-backend-core-first.log`: **281 passed, 25 skipped, 4 warnings**. One skip was pre-existing; 24 were explicit optional assigned integration cases. Subsequent two new Liftoff launch cases also skip under core before their optional fixtures execute.
- Full frontend `npm test`: `/tmp/task3-front-full-green.log`: **72 files, 239 tests passed**. Three initial lease-caller fixture failures were repaired with explicit approved-assignment transport fixtures, preserving the original lease/security assertions.
- `npm run typecheck` passed (`/tmp/task3-types-e2e.log`). `npm run build` passed, including `/study` and `/study/assignments` (`/tmp/task3-front-build-final.log`).
- Final affected auto prefix + `tests/test_study_registry.py tests/test_study_acquisition.py tests/test_assessments.py tests/test_assessment_review_fixes.py tests/test_simulation_runtime.py tests/test_liftoff_endpoints.py tests/test_openmatb_runtime.py`: `/tmp/task3-final-covering.log`: **85 passed, 1 warning** (includes implementation fingerprints and native evidence/restart/source ordering).
- Final shared core prefix + `-rs tests/test_study_registry.py tests/test_assessments.py tests/test_assessment_review_fixes.py tests/test_pvt_endpoint.py tests/test_screen_endpoint.py tests/test_study_acquisition.py`: `/tmp/task3-core-shared-final.log`: **52 passed, 8 optional skips, 1 warning**. Shared behavior is not skipped because optional instruments exist in fixture setup.
- Native repeated HIGH capture/evidence test actually seals event artifacts, discovers the EvidenceCapture through the original native source and checks each shared source link and identical raw event bytes. `/tmp/task3-evidence-red.log` is unfortunately named but is a GREEN extension check: 4 passed; do not count it as RED evidence.
- Browser command from `webui/frontend`: `MATB_PYTHON=/root/repos/MATB/.venv/bin/python PYTHONPATH=/tmp/matb-predictability-testdeps MATB_COMPONENTS=auto PW_TEST_MATCH='**/{study-registry,mission-flow,liftoff}.spec.ts' npm run test:e2e -- --output=/tmp/task3-browser-final-results`. Mission and Liftoff complete through their actual approved assignment caller flows: **2 passed**. The study test initially selected an accelerated/practice URL; its corrected normal-study rerun is recorded below.

### Final browser and core skip closure

Actual normal assigned-study browser rerun: `MATB_PYTHON=/root/repos/MATB/.venv/bin/python PYTHONPATH=/tmp/matb-predictability-testdeps MATB_COMPONENTS=auto PW_TEST_MATCH='**/study-registry.spec.ts' npm run test:e2e -- --output=/tmp/task3-browser-study-final-results` from `webui/frontend`: **1 passed (4.5s)**, `/tmp/task3-browser-study-final.log`. The assertion uses the accessible KSS heading (the same text also exists in an accessibility legend), preserves Spanish researcher preference versus frozen English participant instructions, and reads back the exact persisted assigned attempt as `started` with `assignment_context.locale=en`. Screenshot `/tmp/task3-assigned-pvt.png` was visually inspected. This exercises entry through actual admission, not a ten-minute PVT completion. Mission/Liftoff actual end-to-end acquisition passed in the preceding combined run. The accidental `fast=1` study fixture was corrected because accelerated mode is intentionally practice; that was not an application defect. The independently reproduced late-visit picker reset was an application defect and has its own RED/GREEN unit evidence above.

Focused core skip inventory command uses the backend prefix above, with `MATB_COMPONENTS=core`, `-v -rs`, and these arguments:

```text
tests/test_openmatb_runtime.py tests/test_openmatb_records.py tests/test_study_acquisition.py tests/test_assessments.py::test_optional_source_binds_predeclared_attempt_without_redeclaring_purpose tests/test_assessment_review_fixes.py::test_polar_compatibility_flag_cannot_override_an_assigned_visit
```

Result `/tmp/task3-core-skip-inventory.log`: **16 passed, 26 skipped, 1 warning in 6.43s**. The 26 are the earlier 24 optional skips plus the two final actual Liftoff predecessor launch regressions. All native names below require the enabled `matb-openmatb` component and a real approved native binding; H10 names require `matb-physiology`; Liftoff names require `matb-liftoff`. These integrations run under auto. This does not skip common behavior through an optional all-instrument fixture: the final shared core selection passed 52 tests, including PVT/screen/registry/admission. Historical/practice native source-read and recovery cases continue to run under core (16 pass in this focused inventory).

Exact optional-only names:


- `tests/test_openmatb_runtime.py::test_create_session_generates_versioned_spanish_assigned_condition`
- `tests/test_openmatb_runtime.py::test_cockpit_theme_is_frozen_in_session_and_scenario_provenance`
- `tests/test_openmatb_runtime.py::test_participant_token_is_required_for_acknowledgement`
- `tests/test_openmatb_runtime.py::test_native_process_exit_before_ready_is_reported_immediately`
- `tests/test_openmatb_runtime.py::test_frozen_visual_profile_tampering_fails_closed_before_launch`
- `tests/test_openmatb_records.py::test_new_session_exposes_empty_attempt_and_truthful_receipt`
- `tests/test_openmatb_records.py::test_unbound_and_stale_ratings_cannot_save_to_current_block`
- `tests/test_openmatb_records.py::test_duplicate_scale_save_is_idempotent_and_never_moves_next_block`
- `tests/test_openmatb_records.py::test_saved_ratings_do_not_claim_missing_task_artifacts_or_qualification`
- `tests/test_openmatb_records.py::test_display_disappearing_blocks_preparation`
- `tests/test_openmatb_records.py::test_processor_prevents_overlapping_native_acquisition`
- `tests/test_openmatb_records.py::test_concurrent_duplicate_scale_requests_only_import_once`
- `tests/test_openmatb_records.py::test_scale_endpoint_emits_one_marker_and_receipt_keeps_saved_block`
- `tests/test_openmatb_records.py::test_legacy_import_rollback_cannot_discard_confirmed_ratings`
- `tests/test_openmatb_records.py::test_questionnaire_receipt_uses_its_own_evidence[False-saved]`
- `tests/test_openmatb_records.py::test_questionnaire_receipt_uses_its_own_evidence[True-saved]`
- `tests/test_openmatb_records.py::test_questionnaire_receipt_uses_its_own_evidence[True-missing]`
- `tests/test_openmatb_records.py::test_legacy_questionnaire_receipt_keeps_unknown_without_rating_time`
- `tests/test_study_acquisition.py::test_native_repeated_condition_child_ratings_and_evidence_identity`
- `tests/test_study_acquisition.py::test_h10_supported_binding_assignment_and_current_purpose`
- `tests/test_study_acquisition.py::test_h10_actual_completion_and_restart_follow_assigned_attempt`
- `tests/test_study_acquisition.py::test_native_interrupted_repeat_retains_distinct_rating_target`
- `tests/test_study_acquisition.py::test_liftoff_launch_uses_frozen_prerequisite_instead_of_legacy_grid`
- `tests/test_study_acquisition.py::test_liftoff_launch_does_not_invent_legacy_prerequisite`
- `tests/test_assessments.py::test_optional_source_binds_predeclared_attempt_without_redeclaring_purpose`
- `tests/test_assessment_review_fixes.py::test_polar_compatibility_flag_cannot_override_an_assigned_visit`

### Changed file inventory

The implementation changes these 86 source/test files; this report is the additional documentation artifact.

```text
webui/backend/app/assessment_adapters.py
webui/backend/app/assessment_service.py
webui/backend/app/db.py
webui/backend/app/experiment_catalog.py
webui/backend/app/liftoff_persistence.py
webui/backend/app/liftoff_runtime.py
webui/backend/app/liftoff_schemas.py
webui/backend/app/main.py
webui/backend/app/openmatb_records.py
webui/backend/app/openmatb_runtime.py
webui/backend/app/openmatb_schemas.py
webui/backend/app/physiology_runtime.py
webui/backend/app/physiology_schemas.py
webui/backend/app/routers/participants.py
webui/backend/app/routers/physiology.py
webui/backend/app/routers/pvt.py
webui/backend/app/routers/screen.py
webui/backend/app/routers/study_registry.py
webui/backend/app/simulation_persistence.py
webui/backend/app/simulation_presentation_bindings.py
webui/backend/app/simulation_runtime.py
webui/backend/app/simulation_schemas.py
webui/backend/app/study_admission.py
webui/backend/app/study_bindings.py
webui/backend/app/study_native.py
webui/backend/app/study_policies.py
webui/backend/app/study_registry.py
webui/backend/app/study_registry_models.py
webui/backend/app/study_registry_schemas.py
webui/backend/tests/study_fixtures.py
webui/backend/tests/study_policy_fixtures.py
webui/backend/tests/test_assessment_review_fixes.py
webui/backend/tests/test_assessments.py
webui/backend/tests/test_experiment_safety.py
webui/backend/tests/test_hcf_refresh.py
webui/backend/tests/test_liftoff_endpoints.py
webui/backend/tests/test_liftoff_failures.py
webui/backend/tests/test_openmatb_records.py
webui/backend/tests/test_openmatb_runtime.py
webui/backend/tests/test_physiology_api.py
webui/backend/tests/test_physiology_runtime.py
webui/backend/tests/test_purpose_provenance.py
webui/backend/tests/test_pvt_endpoint.py
webui/backend/tests/test_screen_endpoint.py
webui/backend/tests/test_simulation_endpoints.py
webui/backend/tests/test_simulation_failures.py
webui/backend/tests/test_simulation_runtime.py
webui/backend/tests/test_study_acquisition.py
webui/backend/tests/test_study_registry.py
webui/frontend/e2e/fixtures.ts
webui/frontend/e2e/liftoff.spec.ts
webui/frontend/e2e/mission-flow.spec.ts
webui/frontend/e2e/study-fixtures.ts
webui/frontend/e2e/study-registry.spec.ts
webui/frontend/src/app/openmatb/participant/page.tsx
webui/frontend/src/app/openmatb/setup/page.tsx
webui/frontend/src/app/physiology/polar-h10/page.tsx
webui/frontend/src/app/pvt/page.tsx
webui/frontend/src/app/screen/page.tsx
webui/frontend/src/app/start/page.test.tsx
webui/frontend/src/app/start/page.tsx
webui/frontend/src/app/study/assignments/page.tsx
webui/frontend/src/app/study/page.tsx
webui/frontend/src/components/assessments/AssessmentPages.test.tsx
webui/frontend/src/components/assessments/AssessmentPicker.test.tsx
webui/frontend/src/components/assessments/AssessmentPicker.tsx
webui/frontend/src/components/liftoff/LiftoffSetupForm.test.tsx
webui/frontend/src/components/liftoff/LiftoffSetupForm.tsx
webui/frontend/src/components/mission/setup/MissionSetupForm.test.tsx
webui/frontend/src/components/mission/setup/MissionSetupForm.tsx
webui/frontend/src/components/openmatb/WorkloadQuestionnaire.tsx
webui/frontend/src/components/study/OccasionEditor.tsx
webui/frontend/src/components/study/OptionalBindings.tsx
webui/frontend/src/components/study/PolicyEditor.tsx
webui/frontend/src/components/study/StudyAssignments.tsx
webui/frontend/src/components/study/StudyEditor.test.tsx
webui/frontend/src/components/study/StudyEditor.tsx
webui/frontend/src/lib/assessment-admission.ts
webui/frontend/src/lib/assessments.ts
webui/frontend/src/lib/assigned-attempt.ts
webui/frontend/src/lib/i18n.tsx
webui/frontend/src/lib/openmatb/api.ts
webui/frontend/src/lib/physiology/api.ts
webui/frontend/src/lib/study.ts
webui/frontend/src/types/liftoff.ts
webui/frontend/src/types/simulation.ts
```

Final `git diff --check` passed. Implementation commit: `d3f71b7bb1b0b4dbc848120dd754460f8292ce32` (`Add frozen study plans and assigned acquisition gates`). The complete Task3 range is `1871e899d93086eb45523e8e207f1e8687c67ab4..HEAD`, including the following documentation-only report commit. No push or merge was performed.

## Fix round 1 — review I1–I6

Fix base: `89217b7234728fbbb96bf7015eaafe65a333bfec`. This round addresses the findings in `task-3-review.md` together. Controller package/startup and original lint evidence is recorded in `task-3-controller-verification.md`: physically stripped core and auto application startup/catalog passed at the fix base, while frontend lint had five memoization errors and one internal-navigation warning. Those package results are attributed to the controller at that exact base, not claimed as rerun on this fix.

### Changed behavior by finding

- **I1:** Removed unnecessary memoization around native published preset/instruction/visual lookups. The callbacks no longer capture a broader dependency than their dependency arrays. Study assignment launch uses Next router navigation. No lint rule or warning was suppressed.
- **I2:** The supported native questionnaire must be the immediate post-target assessment. Declared H10 accompaniment of that same native task, in its explicit collection group, may occupy intervening order positions. An intervening assessment, unrelated questionnaire prerequisite, or recovery interval delaying the questionnaire rejects validation/rehearsal/freeze with an actionable immediate-rating limitation. The exact native target may itself be an explicit prerequisite; saving records its immutable exact attempt selection and checks its finished/current-study status. The authoring row and native setup explain the supported sequence. Assigned setup now describes one prescribed condition and immediate ratings, with prior preparation separately prescribed.
- **I2 repeat/source closure:** Native participant display offers an explicit questionnaire-attempt selector. An interrupted questionnaire stays interrupted; an explicit permitted repeat keeps the same target task and has its own draft, raw record and sidecar. Completed questionnaires can likewise be explicitly repeated through the completed native display. A selected questionnaire for another task or an interrupted/terminal-unsaved attempt cannot save. The originally bound questionnaire remains the compatibility default when an older caller omits the new field; it never silently switches to a later attempt. Changed answers require an explicit repeat, while identical retries are idempotent. The first native sidecar is never replaced by later ratings, and evidence processing is not rerun with substituted workload values.
- **I3:** Actual abort passes `operator_stop` into the first terminal native-block transition, including its pending exact-target questionnaire. The later suite synchronization cannot erase that cause. Recovery with no known cause remains `unknown`. The live-handle abort regression checks the actual abort branch and then creates a repeat under a policy permitting only `operator_stop`.
- **I4:** Liftoff assigned setup obtains its visit ordinal/code/day from the immutable assignment context and needs no legacy StudyParticipantContext request. Server preparation and the manifest builder use that same admitted visit and frozen version. The stored Liftoff protocol fields match the assigned manifest's study identity/version. A real assigned visit 16 works with no legacy participant context; actual first-party browser preparation, phase actions, results, questionnaires and sealing pass. Practice retains the existing supported legacy schedule.
- **I5:** Saved drafts are discovered and reopened by their exact server ID. Reopening restores the canonical payload and exposes validation/rehearsal/approval history. Save updates the selected draft in place; edit invalidates rehearsal; freeze retains the actual returned version ID. Both component and actual browser tests perform save → leave/unmount → reopen exact draft → edit → rehearse/freeze.
- **I6:** Stored enum codes remain unchanged. Researchers see English/Spanish labels for preparation placement, affirmative choices, attempt selection, incomplete denominators, missing-data handling, all five independent eligibility requirements, pooling decisions, HCF selection, interruption causes, comparators, supported preparation observation metrics, analysis units and summaries. Short bilingual copy explains exclusion, report-only qualification and reviewed pooling without implying equivalence.
- **Validation-record deliverable:** Added immutable `study_validation` receipts, tied to exact draft ID/hash and timestamp. `POST /study/drafts/{id}/validate` persists and returns a receipt, including issues. Editing does not rewrite previous validation results. `GET /study/drafts/{id}/history` exposes validation receipts, rehearsal receipts and the actual approval. The UI provides history inspection/refresh alongside draft reopening.
- **Maintainability:** The new study components and types are normally formatted. Bilingual policy labels are a focused helper; native assigned questionnaire selection is a separate component around the unchanged instrument response controls. No speculative framework was added.

### Updated downstream contracts — Tasks4/5/7

`StudyValidation` (`study_validation`): `id`, `draft_id`, `draft_sha256`, `issues_json`, `created_at`. The validate response also exposes parsed `issues[]`. History response is `{validations, rehearsals, approval}`; `approval` is a version view or null. Immutable SQL triggers prohibit validation UPDATE/DELETE, as for rehearsal/approval records. Validation calls remain explicit inspectable events; rehearsal/freeze still revalidate independently.

Assignment context now also supplies `study_id`, `assigned_visit:{ordinal,code,scheduled_day}`, and `schedule_sha256` (SHA256 of canonical authored visits). Liftoff freezes those values in its manifest, with `assignment_id` and `study_version_id`. `LiftoffSession.protocol_id/protocol_version` reflect the corresponding assigned study/version. Legacy practice manifests retain their old protocol identity. Engines must consume the frozen assignment rather than infer eligibility from a legacy protocol identifier.

`WorkloadScaleRequest` and frontend `WorkloadScaleSubmission` add optional `questionnaire_attempt_id`. `OpenMatbSessionView` adds nullable `study_assignment_id`. First-party assigned rating submissions always send both the actual `block_instance_id` and selected `questionnaire_attempt_id`. The returned score entry identifies `questionnaire_attempt_id`, `target_attempt_id`, `block_instance_id`, `occasion_id`, condition, locale and instrument version. Acceptance checks both block and questionnaire identity before clearing a draft. Draft keys append the questionnaire UUID, and draft contents record/check it; historical unassigned draft keys stay compatible.

`StudyNativeRating` (`study_native_rating`) is an additive immutable source table. Its primary `id` equals the questionnaire AssessmentAttempt UUID; other fields are `target_attempt_id`, `session_id`, `block_instance_id`, canonical `payload_json` containing the original six NASA-TLX ratings and Bedford value, `payload_sha256`, and `created_at`. Each saved record has an immutable AssessmentSourceLink with `source_table='study_native_rating'`, `source_id=questionnaire_attempt_id`, `role='acquisition'`. The generic raw endpoint exposes this source. Task5 must select that exact source/attempt, not infer a later questionnaire from the original block's ratings role or take an arbitrary score-map entry.

The original block `role='ratings'` association is preserved and continues to identify its original questionnaire, including when that attempt was interrupted. Current assigned questionnaire receipts use their own `study_native_rating` evidence; a subsequently saved repeat cannot make the original interrupted questionnaire appear saved. Genuine legacy records still obtain truthful read-only receipts from original block rating bytes/timestamps, preserving unknown timestamps.

Every assigned rating writes `scales/ratings/{questionnaire_attempt_id}.json`. The first successfully saved rating additionally creates the existing `scales/{assigned_native_occasion_id}.json` projection. Later repeats get distinct score-map entries keyed by their questionnaire ID and never replace that first sidecar or its score entry. Only the block's original questionnaire may populate its original `ratings_json/ratings_saved_at` projection. Task7 must inventory every per-attempt rating file plus its immutable database/source-link record. Original native capture evidence and its previously derived workload remain unchanged; later analysis can select the separately recorded questionnaire explicitly.

The assigned rating writer holds the registry's SQLite write lock, uses the existing same-directory atomic artifact writer, and accepts an already-existing file only if its bytes match. An injected artifact failure rolls back the unsaved questionnaire/source transaction; no false finished state remains. Retrying the same payload succeeds and earlier sidecars remain byte-identical. A conflicting existing artifact fails closed for review instead of being overwritten.

Fingerprint inventory additions: native implementation now includes `webui/backend/app/study_native.py`; questionnaire implementation includes that helper plus `webui/frontend/src/components/openmatb/AssignedWorkloadQuestionnaire.tsx`, alongside the already inventoried WorkloadQuestionnaire, i18n and native runtime files. Existing POSIX logical-path sorting/serialization and original-byte hashing rules remain unchanged. These changed implementations require a reviewed new frozen version; old source reads do not require reapproval.

### Fixture integrity and failure analysis

Controller approved keeping assigned saves independent of legacy Block projection. Concurrent saves now assert one exact immutable rating source, one state advance, identical retry idempotence and rejection of changed answers. The legacy rollback regression directly seeds genuine historical native/rating rows and invokes the real legacy ingestion service with an injected persistence failure; it verifies committed original rating bytes survive rollback. Current questionnaire receipt tests use real assigned saves; the unknown historical receipt regression uses genuine legacy records without a prospective declaration or assignment. No public admission gate is mocked away to recover passing tests.

Initial expanded backend covering run had six failures: one test fixture opened a nested Session on the same in-memory SQLite connection and rolled back its outer participant seed; five exercised obsolete legacy-projection assumptions for newly assigned ratings. The fixture scopes above resolve those contracts. New assigned-store failure/retry coverage separately protects current persistence.

The first actual reopening browser attempt showed the saved draft and exact UUID in the page snapshot, but its exact nested-label locator did not match. Using the accessible `combobox` name exercised the visible control and the entire intended flow passed. This is recorded as a browser locator correction, not a product reopening defect. The unit reopening RED separately reproduced the previously absent feature.

A later frontend covering run exposed an existing test mock race: participant polling returned BETWEEN_BLOCKS before the test submitted ratings, removing the controls mid-input. The fixture now advances the mock server state only when submit is called, preserving all draft-clear-failure assertions. This is an explicit sequencing fix, not retry-only acceptance.

### Verification commands and evidence

Commands ran from the same backend/frontend directories and Python environment as the original report. Backend prefix:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/matb-predictability-testdeps PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 MATB_COMPONENTS=auto /root/repos/MATB/.venv/bin/python -B -m pytest -q -p no:cacheprovider -p anyio.pytest_plugin
```

- RED `/tmp/task3-fix1-red.log`: prefix + `tests/test_study_registry.py::test_validation_history_retains_exact_hash_results_after_edit tests/test_study_acquisition.py::test_native_live_handle_abort_records_operator_cause_and_permits_authored_repeat tests/test_study_acquisition.py::test_liftoff_authored_visit_16_launches_without_legacy_context`: **3 failed** (missing receipt hash, actual unknown abort category, legacy visit rejection). Intermediate GREEN had 2 pass/1 fail because the Liftoff manifest builder had the second legacy schedule dependency; final covering includes all three passing.
- RED `/tmp/task3-fix1-questionnaire-red.log`: prefix + `tests/test_study_acquisition.py -k questionnaire_rejects`: **3 failed, 8 deselected** after initializing actual published native binding fixtures. Those failures prove accepted unexecutable delayed/other-prerequisite/recovery schedules. Final covering includes their rejection and the accepted exact-target/H10 schedule.
- RED `/tmp/task3-fix1-rating-repeat-red.log`: prefix + `tests/test_study_acquisition.py -k explicit_rating`: new explicit questionnaire identity absent from the request schema; later passing coverage exercises independent interrupted and completed repeats, exact target prerequisite, immutable raw records and rollback/retry.
- RED `/tmp/task3-fix1-draft-red.log`: `npm test -- src/components/study/StudyEditor.test.tsx`: **1 failed, 2 passed**, saved-draft reopening missing. Later affected runs include passing reopening/freeze and consequential bilingual-choice coverage.
- Final affected auto `/tmp/task3-fix1-backend-final.log`: prefix + `tests/test_study_registry.py tests/test_study_acquisition.py tests/test_openmatb_records.py tests/test_openmatb_runtime.py tests/test_liftoff_endpoints.py tests/test_experiment_safety.py`: **80 passed, 1 warning, 40.22s**.
- Final atomic-file refinement `/tmp/task3-fix1-atomic-rating-final.log`: prefix + `tests/test_study_acquisition.py::test_native_explicit_rating_attempt_prerequisite_and_independent_repeat tests/test_openmatb_records.py::test_concurrent_duplicate_scale_requests_only_import_once tests/test_openmatb_records.py::test_scale_endpoint_emits_one_marker_and_receipt_keeps_saved_block`: **3 passed, 1 warning, 6.18s**.
- Final shared core `/tmp/task3-fix1-core-final.log`: prefix with `MATB_COMPONENTS=core`, plus `-rs tests/test_study_registry.py tests/test_assessments.py tests/test_assessment_review_fixes.py tests/test_pvt_endpoint.py tests/test_screen_endpoint.py tests/test_study_acquisition.py tests/test_openmatb_records.py::test_legacy_questionnaire_receipt_keeps_unknown_without_rating_time tests/test_openmatb_records.py::test_legacy_import_rollback_cannot_discard_confirmed_ratings`: **55 passed, 14 explicit optional skips, 1 warning, 25.60s**. Shared PVT/screen/registry/admission and genuine historical reads/rollback run. Native/H10/Liftoff skips identify disabled components; none skips common setup merely because optional instruments exist.
- Browser command: `MATB_PYTHON=/root/repos/MATB/.venv/bin/python PYTHONPATH=/tmp/matb-predictability-testdeps MATB_COMPONENTS=auto PW_TEST_MATCH='**/{study-registry,liftoff}.spec.ts' npm run test:e2e -- --output=/tmp/task3-fix1-browser-results`. Actual Liftoff assigned visit 16 without legacy context completed all phase/result/questionnaire/seal steps and accessibility checks: **1 passed**; the other test's locator failure is documented above.
- Corrected actual study browser command uses `PW_TEST_MATCH='**/study-registry.spec.ts'`, output `/tmp/task3-fix1-browser-study-results`, log `/tmp/task3-fix1-browser-study.log`: **1 passed (21.3s)**. It asserts actual same-ID saved draft reopening/edit/validation/rehearsal/approval history, then the persisted started assigned PVT with frozen English and Spanish researcher preference.

- Final frontend command: `npm test -- src/components/study src/components/openmatb/AssignedWorkloadQuestionnaire.test.tsx src/components/openmatb/WorkloadQuestionnaire.test.tsx src/components/liftoff/LiftoffSetupForm.test.tsx src/app/openmatb/participant/page.test.tsx src/app/openmatb/setup/page.test.tsx src/components/assessments/AssessmentPages.test.tsx`: `/tmp/task3-fix1-frontend-green.log`, **8 files, 33 tests passed (19.75s)**. This includes rejection of a response naming the wrong questionnaire while retaining the correct per-attempt draft.
- Final `npm run lint`: `/tmp/task3-fix1-lint-committing.log`, exit 0, no errors or warnings. `npm run typecheck`: `/tmp/task3-fix1-types-final.log`, exit 0. Final `npm run build`: `/tmp/task3-fix1-build-final.log`, exit 0 including /study and /study/assignments; this also typechecks the final source.
- Final built browser closure after preserving the actual returned frozen-version ID uses the same single-study browser command with output `/tmp/task3-fix1-browser-committing-results`: `/tmp/task3-fix1-browser-committing.log`, **1 passed (10.2s)**. No retry setting or weakened assertion was used.
- Final `git diff --check` passed. Implementation/report commit identities and changed-file inventory follow below.

### Remaining limits and warnings

No scientific thresholds, scoring formula, native stimulus timing or instrument task sequence was changed. Delayed native questionnaires remain unsupported and are rejected before approval; only immediate native ratings plus the specified H10 accompaniment are executable here. The new source store preserves later questionnaire observations without substituting them into earlier evidence. Measured preparation, plan execution/HCF and whole-visit resource protection remain Tasks4/5/6, with their existing honest pending markers and fail-closed required preparation. No physical qualification or hardware timing conclusion is claimed.

The current focused backend warning is Starlette's multipart pending deprecation. The original full-suite SQLModel query deprecations and separate statsmodels MLE-boundary convergence warning remain documented from their proper dependency/inferential paths; none was blanket-suppressed. Unrelated passing full suites were reused instead of rerun indiscriminately. The controller's physically stripped-package checks are referenced at the fix base; final package/review decisions remain controller-owned.

### Fix-round commit and file inventory

Implementation commit: `f92997b1c5ee2bb9b26957d411468bbd9fdc9338` (`Fix study authoring and assigned instrument review gaps`). The complete fix range is `89217b7234728fbbb96bf7015eaafe65a333bfec..HEAD`, including the following report-only commit. No push or merge was performed.

```text
webui/backend/app/assessment_adapters.py
webui/backend/app/liftoff_persistence.py
webui/backend/app/liftoff_runtime.py
webui/backend/app/openmatb_records.py
webui/backend/app/openmatb_runtime.py
webui/backend/app/openmatb_schemas.py
webui/backend/app/routers/study_registry.py
webui/backend/app/study_admission.py
webui/backend/app/study_bindings.py
webui/backend/app/study_native.py
webui/backend/app/study_registry.py
webui/backend/app/study_registry_models.py
webui/backend/tests/test_openmatb_records.py
webui/backend/tests/test_study_acquisition.py
webui/backend/tests/test_study_registry.py
webui/frontend/e2e/liftoff.spec.ts
webui/frontend/e2e/study-fixtures.ts
webui/frontend/e2e/study-registry.spec.ts
webui/frontend/src/app/openmatb/participant/page.test.tsx
webui/frontend/src/app/openmatb/participant/page.tsx
webui/frontend/src/app/openmatb/setup/page.tsx
webui/frontend/src/components/liftoff/LiftoffSetupForm.test.tsx
webui/frontend/src/components/liftoff/LiftoffSetupForm.tsx
webui/frontend/src/components/openmatb/AssignedWorkloadQuestionnaire.test.tsx
webui/frontend/src/components/openmatb/AssignedWorkloadQuestionnaire.tsx
webui/frontend/src/components/openmatb/WorkloadQuestionnaire.tsx
webui/frontend/src/components/study/OccasionEditor.tsx
webui/frontend/src/components/study/OptionalBindings.tsx
webui/frontend/src/components/study/PolicyEditor.test.tsx
webui/frontend/src/components/study/PolicyEditor.tsx
webui/frontend/src/components/study/StudyAssignments.tsx
webui/frontend/src/components/study/StudyEditor.test.tsx
webui/frontend/src/components/study/StudyEditor.tsx
webui/frontend/src/components/study/policy-labels.ts
webui/frontend/src/lib/assessments.ts
webui/frontend/src/lib/study.ts
webui/frontend/src/types/openmatb.ts
```
