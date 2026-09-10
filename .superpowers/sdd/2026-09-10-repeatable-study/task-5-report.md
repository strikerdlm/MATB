# Task 5 implementation report

Review base: `80fd2abbb5ca946916e021e1d8b713419586007e` on `codex/repeatable-study`, worktree `/root/repos/MATB/.worktrees/repeatable-study`. Task5 began from Task4 production checkpoint `4e47612a`, paused with thirteen partial files preserved byte-for-byte for the separately reviewed Task4 test-fixture correction, and resumed from the stated review base. No production dataset, original checkout, push, merge, or subagent was used. Root owns independent review and delivery.

## Implemented contracts

### Immutable HCF and legacy fit boundary

`hcf_derivation` stores a canonical, content-addressed `hcf-derivation-v1` snapshot and creation time. The snapshot records plan ID, exact sorted participant/screen/attempt references, raw and scoring hashes, cohort SHA256, mapping source hash/constants, and complete existing HCF estimates. One reference per participant is enforced; duplicate participant references raise rather than weighting repeated screens. Reordering the same reference set gives the same ID. Planned execution selects only eligible designated screen occasions using the authored explicit/first_finished/latest_finished policy. Explicit selection has no fallback. HCF separately checks reference-cohort configuration compatibility across participants.

Existing `SCREEN_VERSION=2`, `K=0.05`, clamp `[0.85,1.15]`, minimum cohort `3`, minimum metric `n=2` and the original `compute_cohort_hcf` math are unchanged. The status remains exploratory. Derivation creation time is outside the content hash, so identical references do not create different identities merely because of time.

`hcf_exploratory_pointer` is the only mutable HCF pointer (`legacy-unambiguous`). Startup/screen ingestion advance that pointer only; they no longer rewrite existing `DepdfFit.hcf_value/hcf_source`. Existing fits and their original curves remain intact. New legacy fits bind an immutable `hcf_fit_snapshot` to the precise derivation using the canonical saved fit. The fit is flushed/refreshed before hashing to normalize SQLite's datetime representation. An old fit with no recoverable binding is labeled `unknown_unrecoverable_legacy_reference_cohort`; historical values are preserved rather than reconstructing a fictional cohort.

`GET /fits`, `/exports/research-context`, and `/exports/research-bundle` accept optional `hcf_derivation_id`; the returned exploratory estimate/curve is a separate field, not a replacement for the original fit. These responses explicitly describe their legacy visit-fit scope. The legacy bundle is not full-study restoration, and planned analyses have their own export endpoint. Legacy inferential entry points remain separate and are never invoked by descriptive execution.

### Exact plan authoring and raw calculators

New approval requires an exact supported metric, original unit, explicit source selectors where needed, and exact installed calculator source/dependency binding. Draft create/save normalizes those bindings; validation rejects stale bindings before approval. Existing frozen plans remain readable through registry APIs, but an old generic/missing/stale analysis binding returns `409 frozen_plan_not_executable` with an honestly dated new-version path. No historical version is rewritten.

The executable catalog is bounded:

- PVT: `pvt.median_rt_ms` (ms), `pvt.lapses` (count), `pvt.kss` (1-9). Original PVT constants, input validation, validity reasons and `_metrics` were moved verbatim into portable `matb_integration/pvt_scoring.py`; the existing router reexports them and keeps its API.
- Screen: `screen.simple_rt` (ms), `screen.hcf` (F/F0), using the original scorer and HCF mapping.
- Native: `openmatb.sysmon_hit_rate` (proportion), `openmatb.track_rmse_deviation` (normalized_cursor_distance). The request must name exact metric IDs from one preserved derivation of the exact capture, matching the entire frozen outcome selector set. The original deterministic native reconciliation runs on the preserved original artifacts and declared derivation version. No source metric is promoted to hardware/human qualification.
- Questionnaire: `questionnaire.rtlx_mean_0_100` (0-100), `questionnaire.bedford` (1-10), using the exact immutable `StudyNativeRating` attempt and its original six dimensions/Bedford, rather than a mutable block sidecar.
- Liftoff: `liftoff.primary.median_lap_time_s` (s), `liftoff.primary.valid_laps` (count), via original `compute_metrics`, original VisibleResults record and canonical telemetry. The supported `liftoff-telemetry-all-v1` canonical serializer omits motor_count; the adapter uses fixed four, grounded in the existing protocol decoder's fixed-four contract. It explicitly records `original_datagram_metadata_recovered=false`, the protocol basis and original artifact bytes. Unsupported context fails with an explicit source error rather than claiming recovery.
- sUAS: `suas.contacts.correct_fraction` (proportion), `suas.coverage.percent` (percent). Exact unique block keys and within-session `individual/mean/median` are frozen in the plan. Original immutable streams/manifests are retained; the existing effective-record stream and reducer run for those exact keys. Missing/ambiguous blocks fail; an arbitrary available block is never selected.
- Physiology: `physiology.mean_hr_bpm` (bpm), from original RR parquet and an exact unique marker label. The existing 300-second window is bounded by the next marker, with existing contact/continuity/validity masks and SQI/minimum-RR criteria. This is a bounded existing calculator, not a new scientific endpoint declaration.

Optional calculators import only when selected. Core shared modules remain import-safe. Generic identifiers, mismatched units, unsupported selectors, ambiguous multi-block summaries, incompatible contrast units and individual summaries over multiple occasions per non-attempt unit fail before approval. Additional native/optional metrics remain unsupported; no requirement to expose every metric was inferred.

### Source, purpose, eligibility, historical selection and pooling

Every planned selection uses exact shared occasion/attempt UUIDs and immutable source associations. Source integer-ID reuse is detected by purpose-provenance identity; archived PVT/screen evidence is unwrapped from the original archive snapshot and labeled with archive identity without looking up a reused original ID. Raw PVT/screen scores are recomputed and checked against stored scores; original optional/native artifact bytes and inventory hashes are retained. Controller lease hashes are removed from research exports.

The integrated historical path resolves a uniquely matching plan occasion only from a current named retrospective occasion classification whose `version_ref` explicitly names that exact frozen version, with matching instrument, phase, order and visit ordinal. Full classification history is snapshotted; `historical=true`, `assignment=None`, original configuration/preparation unknowns and acquisition/planning chronology remain. This is an analysis association, not evidence that the procedure was actually executed. Historical association never creates assignment or admission records. Under an assigned denominator it exposes unavailable coverage (`denominator_coverage=false`); observed started/finished lifecycle can support those explicitly authored modes.

Purpose eligibility examines original declaration history plus current classification. Original explicit study must still currently be study. Original unknown requires named documented retrospective study classification AND frozen-plan permission. `system:migration`, missing provenance, or explicit practice subsequently relabeled study cannot become prospective study.

Separate criterion objects expose passed/required/reason/evidence/href for purpose, source, protocol, preparation, physical timing qualification, human calibration, repeat and interruption, plus exact occasion and denominator coverage. Unknown facts fail the relevant criterion; `report_status` makes that failure visible without pretending it was required or passed. Source completeness, physical qualification, human calibration and preparation are never interchangeable.

Preparation eligibility consumes the original `preparation-admission-v1` admission snapshot and verifies its hash, exact attempt/assignment/version/key/config, selected preparation identity/config hashes, event frontier payload hashes and passed decision event IDs. Later preparation events do not replace the original admitted binding. Current readiness is separately displayed on reopen.

Qualification uses selected linked report records, actual `assessment.status == PASS`, exact capture manifest/source-commit/profile context, named report and binding reviewers, reviewer-attested rationale and absence of revocation. Merely having a `linked_evidence` summary does not pass. FAIL, NOT_TESTED, mismatched and revoked records remain separate negative evidence, and external human-report claim limits are retained.

Configuration reports compare task/instructions/language/visual/input/timing/scoring identity only for observations actually combined within an outcome's declared unit, or a contrast's unit/instrument. A report containing separate PVT/native/H10 outcomes does not pool those instruments. Single observations need no pooling; their unknown configuration still remains unknown. Intended condition differences are retained. Unknown or different within-group configuration requires the frozen policy's named structured attestation `{actor,rationale,reference}`; a vague string/system actor is insufficient. Reports explicitly set `equivalence_claim=false`. HCF retains its separate cross-participant reference-cohort check.

### Frozen input, execution and offline artifact interface (Task6/Task7)

Immutable tables (SQLite UPDATE/DELETE guards):

- `study_analysis_input`: content-addressed ID of `{snapshot,request}`, exact version FK, complete canonical pre-execution snapshot/request, actor, reason, timestamp.
- `study_analysis_execution`: UUID, version FK, plan/data/implementation SHA256, canonical request/snapshot/result, actor, reason, timestamp.
- `study_analysis_artifact`: `(execution_id,path)` primary key, SHA256 and exact immutable blob.
- `hcf_derivation` and `hcf_fit_snapshot` as above.

`freeze_input(db,request)` performs full selection, raw reading/calculation and eligibility checking, saves immutable input, and returns its ID. **It is heavy work**, as are preview, current applicability, execution, bundle construction/compression and selected HCF refresh paths. The caller owns transaction/admission. Task6 must guard the whole operation before it begins, including `GET` current-applicability paths; guarding only POST execute is insufficient.

`execute_frozen(db,input_id)` consumes only the stored snapshot/request, with no later reselection. It rejects both changed calculator source and changed pinned dependency identities with 409, preserving the queued input for restoration of its original environment. The regression inserts a later attempt after freezing and proves it is absent from execution. `execute(db,request)` is the convenience wrapper. Routes currently use existing registry transaction locking; live-visit scheduling/admission belongs to Task6.

API under `/study/analyses`: GET catalog/list/hcf; POST preview; POST execute (empty suffix); POST inputs; POST inputs/{id}/execute; GET {id}; GET {id}/export. `ExecutionRequest` forbids extra fields and includes version_id, exact occasion→attempt IDs, attempt→native metric IDs, attempt→qualification kind/report IDs, participant→HCF attempt IDs, named actor/reason. Route order keeps static resources distinct from execution IDs. `read(...,current=False)` returns saved results without re-reading acquisition state. Default read returns the immutable result plus separate fresh `current_applicability`; reclassification changes that comparison, not old values or figures.

Results are **per declared unit** (participant/visit/attempt) individual values or prescribed mean/median within that unit, plus paired left-minus-right contrasts in original units. There is no cross-unit cohort mean/median, automatic model, inferential test, Bayesian fit, Friedman/Spearman/sign test, or implicit native primary outcome. All assigned/started/finished units according to the authored rule remain represented by denominators, observed/missing identities and reasons. Complete-case exclusion also detects missing required occasions within a pooled unit. Contrast configuration exclusions reconcile observed/missing/denominator after exclusion.

Each export ZIP contains exact `input.json`, `selection.json`, `execution.json`, `result.json`, `figure.svg`, `checksums.json`, `requirements.lock`, `README.txt`, `verify.py`, source tree, preparation provenance source and matching wheels. Source paths are logical relative paths. `implementation.files` fingerprints the packaged calculator/provenance/wheel closure; data, plan, study, implementation and frozen-selection fingerprints are independently checked by the verifier. It then recomputes original raw calculators, HCF estimates/identity, declared aggregates/contrasts and SVG; copied result JSON is not accepted as proof of computation. Checksums are local integrity evidence, not an external signature. The analysis bundle does not claim full workspace restoration.

`implementation_artifacts` currently copies installed `matb_integration` Python/JSON source and the pure replay rules, plus eleven preparation-generation/presentation provenance files. Optional unavailable trees need not exist. Calculator source identity is frozen in the plan, with exact installed dependency versions. The source hash inventory intentionally invalidates new execution against altered code; historical reads/artifact bytes remain available.

Dependency wheels must be prepared **before** execution with `tools/prepare_study_wheels.py PATH`; runtime never downloads them. Configure `MATB_DESCRIPTIVE_WHEELHOUSE`, default `.test-tmp/repeatable-study/descriptive-wheels`. Missing or ambiguous matching wheel fails execution 409. CI now prepares wheels after requirements-dev installation in its Linux/Windows console job. Task7 must include both new `tools/*.py` CLI paths in core distribution/restoration closure, along with the new tables and artifact blobs. Existing core profile tests pass; physically stripped distribution packaging is Task7's ownership.

Local retained wheelhouse is 111 MiB. Versions in the all-supported-kit proof: PyYAML6.0.3, annotated-types0.8.0, numpy2.4.6, pandas3.0.5, pyarrow24.0.0, pydantic2.13.4, pydantic_core2.46.4, python-dateutil2.9.0.post0, scipy1.18.0, six1.17.0, typing-inspection0.4.2, typing_extensions4.16.0. Wheels are platform/Python-specific; the recorded environment must match or corresponding matching wheels must be prepared. The PVT test's expanded analysis bundle is 4.3 MiB; the all-calculator fixture with its installed venv is 598 MiB. Artifact storage duplicates source/wheels per execution and performs ZIP construction in memory; this is deliberately bounded implementation scope, not a deduplicated artifact store. Task6 should account for it as heavy work.

### Researcher UI

`/study/analysis` provides EN/ES plan selection, exact attempt/native/qualification/HCF selections, preview with incomplete denominators and independent criterion snapshots/links, explicit run/freeze, export, reopen by execution ID or URL, side-by-side execution and HCF derivation comparison, and separate current applicability. The output scope explicitly states within-unit descriptions and no cohort mean. The immutable SVG is sandboxed. `StudyEditor` supplies exact catalog selectors/units and source keys/aggregation; `PolicyEditor` supplies named pooling attestation. No participant stimulus flow, instrument geometry or timing prompt was added.

## TDD and focused iteration evidence

All tests use isolated synthetic evidence. Initial rule RED command (backend cwd):

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/matb-predictability-testdeps PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 MATB_COMPONENTS=auto /root/repos/MATB/.venv/bin/python -B -m pytest -q -p no:cacheprovider -p anyio.pytest_plugin tests/test_study_analysis.py
```

RED: collection failed `ModuleNotFoundError: app.study_analysis_rules`, expected before the rule module existed. GREEN: `4 passed in 0.02s`, one existing python_multipart PendingDeprecationWarning. This exact early result was retained in `task-5-progress.md` before the controller-requested pause. Rules covered original purpose history, no fallback, unknown configuration/named rationale, incomplete denominator and paired differences.

The first StudyAnalysis unit RED failed because the component did not exist; after implementation the test passed, covering explicit preview/run and preservation of the missing occasion denominator. Typecheck then exposed the initial incorrect studyCall invocation signature; callers were corrected to the existing `(path,body)` API rather than changing the shared client.

Subsequent focused integration added actual PVT save/execute/reclassify/reopen/export; native deterministic replay and qualification PASS/FAIL/NOT_TESTED/revocation/context; immutable HCF cohort growth/permutation; original archive identity under integer reuse and assigned versus finished historical denominators; integrated multi-outcome/condition contrast; complete-case within-unit missingness; exact frozen queued input; optional Liftoff/sUAS/H10 calculators and fresh offline installation. Fixture failures were corrected against existing contracts (sUAS synthetic manifest thresholds/active aircraft count, existing recorder/packet fields), without changing original instrument math or inventing scientific thresholds.

Final queued-dependency regression RED is retained at `.test-tmp/repeatable-study/task5-final/dependency-red.log`: same pytest command with `-k frozen_job` produced `1 failed, 13 deselected`, `Failed: DID NOT RAISE HTTPException` after the installed dependency identity was changed after input freeze. GREEN is included in final 103-test affected gate. The saved input remains byte-identical and changed dependencies fail 409 before derivation/artifact work.

An initial affected-test command named nonexistent `tests/test_exports.py`; collection stopped without running tests. Its output is retained as `backend-affected-missingpath.log`; the corrected covering command uses existing test_endpoints.py/test_body_limits.py and passed. It is not counted as validation. Initial wheel setup without the isolated dependency path could not see pyarrow; corrected setup used the documented interpreter/PYTHONPATH. Two npx formatter discovery attempts hit EAI_AGAIN; the already installed cached Prettier CLI was used without toolchain/package changes. These failures are not presented as clean tests.

## Final gates and retained evidence

All logs below are under `.test-tmp/repeatable-study/task5-final/`. Backend commands use the exact environment/prefix above, no pytest cache/bytecode and the supported escalated execution. Sources were frozen during hash/attestation and replay runs.

1. Full backend auto suite: same prefix followed by no test selection; `445 passed, 1 skipped, 9 warnings in 251.83s`, `backend-auto.log`. This is pre-final-localized-fixes evidence, preserved rather than rerun unchanged. Warnings: existing python_multipart deprecation (1), existing legacy Liftoff MixedLM convergence (1), existing SQLModel query deprecations (7). No new warning category.
2. Final affected backend command appended `tests/test_study_analysis.py tests/test_study_calculators.py tests/test_study_registry.py tests/test_study_acquisition.py tests/test_study_preparation.py tests/test_hcf_refresh.py tests/test_screen_endpoint.py tests/test_pvt_endpoint.py tests/test_fit_trigger.py tests/test_endpoints.py tests/test_body_limits.py tests/test_evidence.py tests/test_evidence_qualification.py`: **103 passed, 1 existing python_multipart warning in 89.56s**, `backend-final.log`. Covers final execution/selection/SVG fingerprints, normalized fit timestamp, dependency drift and both isolated offline proofs. Earlier intermediate final-localized gate also passed103 in82.71s (`backend-affected-final.log`).
3. Core profile command changes MATB_COMPONENTS to core and selects `tests/test_study_analysis.py tests/test_study_calculators.py tests/test_study_registry.py tests/test_study_acquisition.py tests/test_study_preparation.py tests/test_component_lifespan.py -k 'not selected_calculator_wheels and not execution_freezes'`: **45 passed, 16 optional-component skips, 2 deselected, 1 existing python_multipart warning in22.29s**, `backend-core-final.log`. The two deselections are the expensive fresh-venv proofs already executed in final auto mode; no core-specific behavior is claimed from those deselections.
4. Root instrument command: same Python/no-cache environment, `MATB_COMPONENTS=auto`, no anyio plugin needed; `tests/screen tests/suhir/test_hcf.py tests/test_evidence_pipeline.py tests/liftoff/test_metrics.py tests/suas/test_mission_metrics.py tests/physiology/test_hrv_analysis.py`: **54 passed in3.00s, no warnings**, `instruments-final.log`.
5. Full frontend `npm test`: **78 files, 262 tests passed in115.53s**, `frontend-units.log`. Covers all shared changes; subsequent localized analysis-only updates were checked by the focused final gate. No repeated unchanged broad frontend run.
6. Frontend `npx vitest run src/components/study`, `npm run typecheck`, `npm run lint -- --max-warnings=0`, and supported escalated `npm run build`: **15 tests/5 files, typecheck, zero-warning lint and production build passed**; `frontend-study-final.log`, `typecheck-final.log`, `lint-final.log`, `build-final.log`. A final localized browser-accessibility amendment is recorded below with its covering gates.
7. Browser initial run used `MATB_PYTHON=/root/repos/MATB/.venv/bin/python PYTHONPATH=/tmp/matb-predictability-testdeps PYTHONDONTWRITEBYTECODE=1 PW_TEST_MATCH='**/study-*.spec.ts' npx playwright test --config=playwright.config.ts` from frontend: **14 passed, 1 failed in4.4m, zero retries**. The failure was the new analysis plan select accessible name (`getByLabel("Frozen plan", {exact:true})`, timeout); the fourteen unchanged registry/preparation workflows passed. The exact initial log is `browser-red.log`; screenshot/error context is preserved in `browser-red-artifacts/`; fixture DB/raw paths remain `.suas-e2e/241434/`. Final new-case rerun is recorded below; no fresh all-15-run claim is made.

Fresh offline evidence from final backend run:

- `/tmp/pytest-of-root/pytest-151/test_execution_freezes_raw_val0/bundle/offline-proof.json`: actual exported execution replay, `{"status":"reproduced","raw_attempts":1,"automatic_model":null}`. Corresponding input/result/selection/execution/checksum/source/wheel files and replay-venv remain under that test root.
- `/tmp/pytest-of-root/pytest-151/test_selected_calculator_wheel0/offline/isolation-proof.json`: `offline_source_isolated`, with every imported `matb_integration` module's absolute path under that bundle's own `source/`. Includes portable PVT, original screen scorer/native reconcile, Liftoff metrics, sUAS reducer and physiology analysis. The proof executes Liftoff median12 and physiology60bpm using packaged source, not just imports.
- Both venvs use `system_site_packages=False`; inherited PYTHONPATH/PYTHONHOME/VIRTUAL_ENV are removed; pip and execution run with `-I`, `--no-index`, matching bundled wheels and exact lock. No `/tmp/matb-predictability-testdeps` or checkout imports can satisfy the isolated proof. Network installation is not used. Original artifact bytes/fingerprints remain in the package.

## Self-review, limits and downstream work

Batched self-review corrected multi-instrument overbroad pooling; ensured only contributing observations are checked; kept HCF reference-cohort comparison separate; reconciled contrast exclusions; normalized new-fit snapshot timestamp; added execution/selection fingerprints and SVG recalculation; added URL reopen; and rejected queued dependency drift. Review also confirmed no automatic inferential entry point, no generic executable outcome, no practice-to-study laundering, and no historical assignment fabrication. Source and raw/generated evidence paths were preserved.

Coverage is strongest at the integrated core PVT/history/HCF/plan pipeline and deterministic optional calculators. The all-calculator kit proves isolated imports and selected computations; this task does not claim physical sensor/native hardware qualification, human calibration, live optional simulator acquisitions, or full-study restoration. The optional raw adapters operate on immutable artifacts and explicit missing-context errors. Timing/human qualification remains its independent report contract. Local plan attestation does not establish absence of prior result inspection. Current-applicability recomputation is separate from the frozen result and may be unavailable if the required historical implementation is no longer installed.

Task6 owns whole-visit heavy-operation guards/queue admission; Task7 owns full distribution/restoration wiring and full release verification. New CLI paths and all immutable blob tables must be included there. The artifact kit stores matching current-platform wheels and cannot promise arbitrary cross-platform replay. No new dependencies/framework versions were installed into project manifests and no scientific math was changed.

## Changed files

- `.github/workflows/matb-ci.yml`
- `webui/backend/app/db.py`
- `webui/backend/app/hcf_refresh.py`
- `webui/backend/app/ingestion.py`
- `webui/backend/app/main.py`
- `webui/backend/app/routers/exports.py`
- `webui/backend/app/routers/fits.py`
- `webui/backend/app/routers/pvt.py`
- `webui/backend/app/routers/screen.py`
- `webui/backend/app/study_admission.py`
- `webui/backend/app/study_bindings.py`
- `webui/backend/app/study_policies.py`
- `webui/backend/app/study_registry.py`
- `webui/backend/app/study_registry_schemas.py`
- `webui/backend/tests/study_policy_fixtures.py`
- `webui/backend/tests/test_hcf_refresh.py`
- `webui/frontend/e2e/study-fixtures.ts`
- `webui/frontend/src/components/study/PolicyEditor.tsx`
- `webui/frontend/src/components/study/StudyEditor.tsx`
- `webui/frontend/src/lib/study.ts`
- `matb_integration/analysis/study_calculators.py`
- `matb_integration/pvt_scoring.py`
- `tools/prepare_study_wheels.py`
- `tools/verify_study_descriptive.py`
- `webui/backend/app/hcf_derivations.py`
- `webui/backend/app/routers/study_analysis.py`
- `webui/backend/app/study_analysis.py`
- `webui/backend/app/study_analysis_bundle.py`
- `webui/backend/app/study_analysis_catalog.py`
- `webui/backend/app/study_analysis_eligibility.py`
- `webui/backend/app/study_analysis_models.py`
- `webui/backend/app/study_analysis_rules.py`
- `webui/backend/app/study_analysis_sources.py`
- `webui/backend/tests/test_study_analysis.py`
- `webui/backend/tests/test_study_calculators.py`
- `webui/frontend/e2e/study-analysis.spec.ts`
- `webui/frontend/src/app/study/analysis/page.tsx`
- `webui/frontend/src/components/study/StudyAnalysis.test.tsx`
- `webui/frontend/src/components/study/StudyAnalysis.tsx`
- `.superpowers/sdd/2026-09-10-repeatable-study/task-5-report.md` (force-added durable report).

## Final localized browser amendment

The browser RED found the wrapped select label included option text in the computed accessible name. Live isolated-page inspection confirmed exact-name count0. Added explicit translated `aria-label` without relaxing the test; removed a nested main landmark from the new component (the app shell already owns main). No backend calculator, plan binding, instrument or preparation source changed. Existing14 browser cases and final backend/replay gates therefore remain applicable. Final localized commands: `npx vitest run src/components/study` **15 passed/5 files in9.19s**; `npm run typecheck`, `npm run lint -- --max-warnings=0` and `npm run build` all passed with zero lint warnings. Logs are `frontend-accessibility-final.log`, `typecheck-accessibility-final.log`, `lint-accessibility-final.log`, `build-accessibility-final.log`. Final new browser case command: `MATB_PYTHON=/root/repos/MATB/.venv/bin/python PYTHONPATH=/tmp/matb-predictability-testdeps PYTHONDONTWRITEBYTECODE=1 npx playwright test --config=playwright.config.ts e2e/study-analysis.spec.ts`: **1 passed in9.6s, no retries**, `browser-analysis-final.log`. Its fixture root is `.suas-e2e/245043/`. Together with14 unchanged passing cases, every selected workflow passed across the two stated runs; this is not one fresh all15 run. Browser output retains the existing NO_COLOR/FORCE_COLOR environment warning, not a new application warning. The isolated import proof has68 imported matb_integration modules, all under its own source tree.

Final staging check found extra blank lines at EOF in the newly moved PVT scorer and pure rule module. Removed only those blank lines; because these bytes are fingerprinted, reran the two raw/offline proof tests on frozen final bytes. No scientific or executable behavior changed. Exact proof result/paths are recorded below.

Final fingerprint proof command used the same documented backend pytest prefix, `tests/test_study_analysis.py tests/test_study_calculators.py -k 'execution_freezes or selected_calculator_wheels'`: **2 passed, 17 deselected, 1 existing python_multipart warning in26.79s**, `offline-frozen-bytes-final.log`. Fresh final exported execution proof: `/tmp/pytest-of-root/pytest-153/test_execution_freezes_raw_val0/bundle/offline-proof.json`; all-calculator import proof: `/tmp/pytest-of-root/pytest-153/test_selected_calculator_wheel0/offline/isolation-proof.json` (68 imports, all under its packaged source). Earlier pytest-151 evidence remains retained separately. No source mutations followed these final proofs.

Final actual exported fixture identities:

- `id`: `eae25f3b-cb63-469c-b9ca-6ee8d0cd5ac0`.
- `plan_sha256`: `45a7a1dcd5a31b10f3d8f9484cf254b07fcdbbc4243cec04726299c328390e74`.
- `data_sha256`: `039d9f9d705d942517f6ed2cc3161def2709dcfa8cc9378fb11daf23ed0d3c87`.
- `implementation_sha256`: `351923e1b40af76eba42d29f158c397641342af6f152528803526f2031e08fb0`.
- `checksums.json` SHA256: `00e429e3f0344d2866b853281a6a7933db815e9e1c48e4e4eeae35d0346f2f54`.

Final `git diff --cached --check` passes after EOF cleanup. Task5 complete; independent review remains root-owned. Expected release followups remain Task6 heavy-work admission and Task7 distribution/full-study restoration, with no claim those followups are implemented here.
