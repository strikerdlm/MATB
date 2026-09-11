# Task 6 implementation report — whole-visit station reservation and bounded jobs

Task owner: study_acquisition. Worktree `/root/repos/MATB/.worktrees/repeatable-study`, branch `codex/repeatable-study`; base `e8496c171e22b69a4a80219c720e14862f0efd9b`. No push, merge, independent reviewer, extra implementer, production dataset migration, scientific threshold change, or stimulus change. User explicitly waived re-review. The original checkout and previous retained evidence remain intact.

## Implemented contracts

`station_resources.py` adds durable SQLite `station_state`, `station_job`, and named `station_event` records. Every admission/queue/maintenance/recovery mutation acquires the singleton writer row before reading availability. Real competing file-backed SQLite writers are tested. This complements, and does not replace, the existing single-backend database/PID lease. `main.lifespan` acquires that lease before schema, provenance, HCF, or recovery writes.

The reservation owner is the authoritative frozen study assignment, participant and visit. It starts at actual collection and persists through individual task completion, ratings, recovery, and the next prescribed task, until explicit researcher closure. Standalone timed practice releases after its actual acquisition ends. At most one foreground timed acquisition is admitted. Physiology may accompany only the explicitly frozen matching foreground occasion, participant, visit, group and accompanying key. Held native preflight keeps its actual source identity and PID while idle across baseline; initialization must finish before baseline and new expensive initialization cannot enter an already protected visit. Actual native release is admitted before task timing advances. Before-baseline native practice/evidence grading and the Task4 prescribed-later native-practice capability restriction remain intact.

Generic browser start admits PVT and the entire screen battery before stimulus scheduling. `PvtRunner` awaits its onStart promise before taking its timing origin; rejection stays in preparation. Repeated starts cannot create parallel browser ownership. Runtime-backed generic start/finish calls return `runtime_start_required`/the corresponding controller requirement; native, H10, Liftoff and mission controllers admit and synchronize their exact source attempt at the actual start/terminal boundary. Their setup pages read the selected attempt without falsely marking acquisition started. Task4 original preparation admission IDs/frontiers remain frozen in the same admission transaction.

Native previews also acquire standalone timed ownership. Native launch failures release a known failed start; actual PID/handle evidence remains available during recovery. Native individual completion schedules optional evidence processing but never releases the study visit. H10 samples, markers and essential raw Parquet/manifest closure remain operational with heavy jobs queued. Mission finalization first durably closes raw recording; replay, checksums and the existing calculators/debrief are deferred in a durable source job. The existing immutable raw files, runtime/source identity, numerical code and final live-frame binding are retained.

## Heavy work and deferred identity

`station_http.py` admits before multipart spooling. Protected uploads to ingest and Liftoff physiology-link are refused with 409 without consuming request bytes; retry after explicit close. Idle uploads own exclusive heavy capacity before body parsing, with existing plus new endpoint byte limits (6 MiB Liftoff result/HRV, 8 MiB PVT/screen raw). Deferred JSON request bodies are capped at 64 KiB; total serialized payload at 128 KiB. User queue capacity is 32 active jobs, deduplicated by exact kind/payload. One actual heavy worker owns capacity; foreground starts fail while it runs. Source-derived native/mission work uses a durable `waiting_capacity` outbox if the user queue is full, so indispensable source closure cannot lose its subsequent processing request. The outbox is not a public unbounded request queue; it corresponds to durable acquired source records.

Explicit guarded inventory: ingest/ingest-evidence, evidence reconcile/input freeze/capture export, classical/Bayesian/Liftoff analysis, research bundle/context, exploratory screen/fits, descriptive preview/input freeze/execute/export/current refresh, H10 bundle/analysis, Liftoff bundle/seal/physiology link/retry, mission bundle/debrief, geography preparation/promotion, experiment compilation, and actual native preparation grading. Internal native evidence, HCF refresh and mission finalization use the same station policy. Metadata/status/source paging and bounded recording stop/markers remain available. There is no general runtime backup API to invent; exclusive maintenance is the explicit local entry condition for administrative backup/restore tooling.

Marked deferred responses are HTTP202 with `X-MATB-Station-Job` plus `{job_id,status,station_url,next_action}`. The frontend does not parse those as completed scientific results. When idle and FIFO eligible, existing endpoint success semantics are preserved. Replay retains the exact request, appropriate local controller header, body, and selection cutoff; authentication/cookie headers are not persisted. Response bytes are retained up to 128 MiB in `station-job-artifacts/<uuid>.response`, with status/content headers and source cutoff metadata.

Frozen descriptive execution queues the exact immutable input ID. For a new selection, a metadata-only snapshot records the exact occasion and attempt frontier at acceptance before any raw decoding/calculator work; delayed first/latest selection cannot include a later attempt or newly assigned participant. The stored semantics explicitly distinguish the frozen occasion/attempt set from eligibility/source availability observed when exclusive execution begins. Serving a saved analysis is read-only and returns its immutable saved evidence plus an explicit pending current-applicability state. POST refresh is separately heavy. Current changed criteria/errors/readiness are rendered independently of frozen criteria; criterion links now point to exact provenance/preparation/qualification/occasion resources with the proper API base. Saved/reopened read-only and Start a new analysis reset behavior remain preserved.

## Ownership, shutdown and recovery

Queued cancellation is immediate. Running cancellation sets `cancelling` and retains ownership until the actual operation returns. Async await cancellation is not treated as termination: it marks uncertain ownership. Detached Bayesian threads and geography jobs are waited to actual completion; worker shutdown is bounded to 30 seconds, and unconfirmed live writing retains the backend lease until PID exit. Worker exceptions record failure and release only confirmed completed execution. Jobs are durable across restart: queued work is retained; interrupted running work is marked failed rather than silently resumed.

Restart marks outstanding collection ownership uncertain and exact started attempts interrupted with unknown cause. Browser pagehide/unmount reports unknown interruption; neither navigation nor network disconnection establishes physical station idle. No expiry silently resumes or releases a lost acquisition. Recovery requires named researcher idle verification and server inspection of known native PIDs/handles, active physiology recording and active mission runtime. Native PID still alive blocks false idle recovery. Ordinary close is refused while lanes/uncertain acquisition remain. Browser network loss without page lifecycle delivery is conservatively still reserved until explicit researcher recovery; there is no heartbeat-based inference of scientific cause.

## Researcher API and UI

- GET `/station`: reservation, active/held lanes, maintenance, active jobs and block state.
- POST `/station/close`: `{actor,reason}`; close only confirmed stopped collection.
- POST `/station/recover-idle`: `{actor,reason}`; explicit verified idle recovery after uncertainty, preserving interrupted history.
- POST `/station/maintenance`: `{actor,reason,enabled}`; admission is atomic and blocked by acquisition or running work.
- GET `/station/jobs`, GET `/station/jobs/{id}`, POST `/station/jobs/{id}/cancel`, GET `/station/jobs/{id}/artifact`, GET `/station/events`.
- Actor is bounded to 200 characters and reason to 2000. Job/event lists return at most 100 rows. Artifact paths are derived from server UUID identity, not client paths.

Bilingual `/station` displays reservation/held runtime identities, job status/errors, artifacts, cancellation ownership explanation, researcher close/recover/maintenance actions, and links to the actual assigned/native/H10 controls. Researcher sidebar links to it. Pending analysis/export/import calls point to this concrete next action.

## RED/GREEN evidence and retained source

All Task6 artifacts below are under `.test-tmp/repeatable-study/task6` unless absolute. No cited pytest basetemp was reused. `final-source-1.json` was superseded: network `npx prettier` failed with EAI_AGAIN; the installed cached formatter then completed. `format-local.log` and `format-fixtures.log` capture successful formatting before the final source manifests. `git diff --check` passed. Source stayed frozen throughout each fingerprinted verification run; later corrections were made only after the affected run ended or was stopped. Generated tracked Python cache files from the root contract environment are excluded from source identity and this task's commit.

Initial RED (`red.log`): the three new resource tests failed with ModuleNotFoundError for station_resources before implementation. Iteration evidence is retained, including 28-pass focused integration; actual DetachedInstanceError at worker handoff fixed with non-expiring job DTO sessions; native launch-failure lane leak fixed; all 67 affected integration tests passed in `integration7.log` (74.85 s). Older immediate-heavy-work and generic-runtime-start fixtures were updated to exercise the new explicit closure/controller contracts rather than bypassing admission.

Backend command prefix, run from `webui/backend`:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/matb-predictability-testdeps PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 MATB_COMPONENTS=auto /root/repos/MATB/.venv/bin/python -B -m pytest -q -p no:cacheprovider -p anyio.pytest_plugin
```

Full backend, `--basetemp=../../.test-tmp/repeatable-study/task6/final-auto-evidence-1`: `backend-final1.log` recorded 451 passed, 1 skipped, 10 failed, 9 warnings in 292.10 s. All ten failures were old caller/isolated lifecycle fixture contracts: explicit visit closure before cross-participant cohort/import work, runtime-owned H10 start, and mocks disabling DB startup but omitting new station recovery/worker lifecycle. Only those fixtures changed for this backend correction; the later frontend-only navigation transport correction is documented below. The affected six complete modules (`test_assessment_review_fixes.py test_component_lifespan.py test_hcf_refresh.py test_liftoff_failures.py test_liftoff_system.py test_screen_endpoint.py`) passed all 36 tests in 27.18 s with unique `final-auto-fixes-evidence-1`; log `backend-fixes-final1.log`. Together this covers every test from the full run successfully on unchanged production bytes; the initial full-run failure is disclosed, not relabeled a clean exit.

Core profile: same command with `MATB_COMPONENTS=core`, `tests/test_station_resources.py tests/test_study_acquisition.py --basetemp=../../.test-tmp/repeatable-study/task6/final-core-evidence-1`: 12 passed, 12 explicitly optional-component skips, one existing multipart warning, 7.81 s (`core-final1.log`). The new cross-component station module passes in core and auto.

Root executed required independent gates without a reviewer or source mutation: native 854 passed/8.48 s (`native-final.log`, `native-final.xml`, `final-native-evidence-1`); contracts 583 passed/9 skips plus seven environment-only failures, then all seven passed/15.40 s after using required polar-python1.1.1/bleak3.0.2 in isolated `/tmp/matb-task6-transport-testdeps` and outside-repo export basetemp `/tmp/matb-task6-contracts-final-envfix-1`. Combined all 590 contract tests exercised successfully (`contracts-final.log`, `contracts-envfix.log` and JUnit counterparts). Documentation check passed (`documentation-final.log`). Core dry-run passed provisionally but uses base committed source and explicitly reports dirty tree; it is not final physical Task6 package evidence. Task7 owns physical export closure and the existing warnings/Windows presentation flake.

Frontend full first run: 267 passed, three runtime setup mock failures; corrected mocks now use getAttempt for controller-owned setup, preserving lease assertions. Final frontend results and browser results are recorded below when complete.

## Software-only load matrix

Runnable command from repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=webui/backend:/tmp/matb-predictability-testdeps /root/repos/MATB/.venv/bin/python -B tools/station_load_matrix.py --output .test-tmp/repeatable-study/task6/load-final-1
```

Retained `load-final1.log`, `load-final-1/observations.json`, separate SQLite files and real raw Parquet/manifest artifacts for foreground_collection, ratings_gap and recovery_gap. Each scenario exercises actual SimulatedPolarTransport decoding, real PolarCaptureManager queues, raw markers, durable closure, heavy queue denial and subsequent explicit close/claim. Each retained 40 RR intervals, 520 ECG samples, 200 ACC samples, zero overflow and no incomplete reasons; five heavy jobs stayed deferred. Sampled queue occupancy maximum was 0 of 512 packets (polling observation, not proof of zero transient occupancy). Scheduler maximum gaps were 12.633, 11.582 and 11.965 ms; raw closure took 48.454, 40.996 and 44.790 ms; total disk bytes were 1,031,397, 1,031,401 and 1,031,422 respectively. No threshold is asserted from these measurements.

These are software observations only: no BLE radio, physical display latency/frame timing, external simulator/controller, native stimuli, or hardware qualification. The foreground labels are an explicit station model, alongside the real simulated H10 pipeline. Actual native same-identity/held admission is covered separately in runtime integration tests. The harness refuses an existing output directory, preserving earlier observations.

## Retained scientific continuity

The full backend retained Task5 export/verification tests on the unchanged production snapshot. `final-auto-evidence-1/test_execution_freezes_raw_val0/bundle/offline-proof.json` reads `{"status":"reproduced","raw_attempts":1,"automatic_model":null}`. The fresh no-index replay environment, source kit, lockfile, wheels, raw inputs, checksums and frozen result remain beside it. HCF raw-rebuild, excluded-observation and scientific-inconsistency export fixtures remain in that same nonrotating basetemp. Their successful tests preserve original grouping association, immutable input and descriptive-only reproduction semantics. This does not qualify production or hardware data.

## Final verification completion

The final source6 completion evidence below supersedes earlier iteration snapshots.

Prior final-run production/source identity: `final-source-4.json` SHA256 `fafc1975edec4cdf9b12119fb6f434fc877ba88ab2191f8ab05ed3656a03a6ad`, 59 changed/new source and test files. Source2 SHA256 `54c7f0b1354ac43a9564187e4bafdaf92f2b95162ab0fc8c7a74f764ffe12f8d`; source3 adds only caller fixtures; source4 adds only the explicit route-matrix tests. All production file hashes remained identical across these snapshots. A post-gate comparison found no source4 mismatches. `retained-artifact-identities.json` gives byte counts and SHA256 identities for source manifests, load observations, offline proof, export checksums and retained HCF/exclusion zip exports. Offline proof SHA256 `89c1fb0cb87cec3b031d80d34f3311b0c1d0f94a39a244ced118476811a9c16b`; load observations SHA256 `966d3c4741f9e9762c4e265aecbf5553740d6970e3e8ef6bc6169105b6e7c31f`.

Final frontend commands, from `webui/frontend`, with supported escalated execution:

```sh
npm test
npm run typecheck
npm run lint -- --max-warnings=0
npm run build
```

`frontend-final2.log`: **81 files, 270 tests passed**, 105.13 s. `typecheck-final2.log`, `lint-final2.log`, `build-final2.log`: all exit0; strict lint has zero warnings. This source3 frontend pass preceded the later browser-discovered navigation transport correction; final source6 frontend verification below supersedes it.

Final explicit heavy-route matrix adds independent concrete paths, not a test generated from the middleware regex list: 26 deferred operations and three refused uploads each during collection, ratings and recovery. Same backend prefix plus `tests/test_station_resources.py`, once auto with `--basetemp=../../.test-tmp/repeatable-study/task6/final-station-matrix-auto-1`, once core with `final-station-matrix-core-1`: **15 passed auto/3.72 s; 15 passed core/4.87 s**, only existing multipart warning. Logs `station-matrix-auto-final.log`, `station-matrix-core-final.log`. This also retains actual SQLite races, active thread cancellation, PID, startup owner, held initialization and metadata cutoff cases.

Exact root gate commands (all prefixed `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/matb-predictability-testdeps PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`):

```sh
# cwd openmatb
/root/repos/MATB/.venv/bin/python -B -m pytest tests -q -p no:cacheprovider --basetemp=../.test-tmp/repeatable-study/task6/final-native-evidence-1 --junitxml=../.test-tmp/repeatable-study/task6/native-final.xml
# cwd repository
/root/repos/MATB/.venv/bin/python -B -m pytest tests -q -p no:cacheprovider --ignore=tests/suas --ignore=tests/liftoff --ignore=tests/documentation --basetemp=.test-tmp/repeatable-study/task6/final-contracts-evidence-1 --junitxml=.test-tmp/repeatable-study/task6/contracts-final.xml
/root/repos/MATB/.venv/bin/python -m pip install --target /tmp/matb-task6-transport-testdeps --no-deps polar-python==1.1.1 bleak==3.0.2
# same pytest env, with /tmp/matb-task6-transport-testdeps first in PYTHONPATH
/root/repos/MATB/.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/physiology/test_packet_decoding.py::test_pmd_golden_vectors_decode_signed_units_and_endianness tests/test_public_core_export.py::test_public_core_selection_fails_closed_without_git_metadata tests/test_public_core_export.py::test_candidate_export_has_hashed_inventory tests/test_public_core_export.py::test_candidate_records_an_explicit_clean_source_state tests/test_public_core_export.py::test_custom_publish_policy_is_the_exact_manifest_embedded_in_artifact tests/test_public_core_export.py::test_candidate_backend_runs_without_optional_product_components --basetemp=/tmp/matb-task6-contracts-final-envfix-1 --junitxml=.test-tmp/repeatable-study/task6/contracts-envfix.xml
PYTHONDONTWRITEBYTECODE=1 /root/repos/MATB/.venv/bin/python -B scripts/verify_documentation.py
PYTHONDONTWRITEBYTECODE=1 /root/repos/MATB/.venv/bin/python -B scripts/export_public_core.py --dry-run
```

## Changed files

- `tools/station_load_matrix.py`
- `webui/backend/app/assessment_service.py`
- `webui/backend/app/body_limits.py`
- `webui/backend/app/db.py`
- `webui/backend/app/liftoff_persistence.py`
- `webui/backend/app/liftoff_runtime.py`
- `webui/backend/app/main.py`
- `webui/backend/app/openmatb_runtime.py`
- `webui/backend/app/physiology_runtime.py`
- `webui/backend/app/routers/assessments.py`
- `webui/backend/app/routers/station.py`
- `webui/backend/app/routers/study_analysis.py`
- `webui/backend/app/simulation_runtime.py`
- `webui/backend/app/station_http.py`
- `webui/backend/app/station_mission.py`
- `webui/backend/app/station_resources.py`
- `webui/backend/app/station_worker.py`
- `webui/backend/app/study_admission.py`
- `webui/backend/app/study_analysis.py`
- `webui/backend/app/study_analysis_eligibility.py`
- `webui/backend/tests/conftest.py`
- `webui/backend/tests/station_fixtures.py`
- `webui/backend/tests/test_assessment_review_fixes.py`
- `webui/backend/tests/test_assessments.py`
- `webui/backend/tests/test_component_lifespan.py`
- `webui/backend/tests/test_endpoints.py`
- `webui/backend/tests/test_hcf_refresh.py`
- `webui/backend/tests/test_liftoff_endpoints.py`
- `webui/backend/tests/test_liftoff_failures.py`
- `webui/backend/tests/test_liftoff_system.py`
- `webui/backend/tests/test_screen_endpoint.py`
- `webui/backend/tests/test_simulation_endpoints.py`
- `webui/backend/tests/test_simulation_runtime.py`
- `webui/backend/tests/test_station_resources.py`
- `webui/frontend/e2e/station.spec.ts`
- `webui/frontend/src/app/openmatb/setup/page.tsx`
- `webui/frontend/src/app/physiology/polar-h10/page.tsx`
- `webui/frontend/src/app/station/page.tsx`
- `webui/frontend/src/components/assessments/AssessmentPages.test.tsx`
- `webui/frontend/src/components/layout/SidebarNav.tsx`
- `webui/frontend/src/components/liftoff/LiftoffSetupForm.test.tsx`
- `webui/frontend/src/components/liftoff/LiftoffSetupForm.tsx`
- `webui/frontend/src/components/mission/setup/MissionSetupForm.test.tsx`
- `webui/frontend/src/components/mission/setup/MissionSetupForm.tsx`
- `webui/frontend/src/components/pvt/PvtRunner.test.tsx`
- `webui/frontend/src/components/pvt/PvtRunner.tsx`
- `webui/frontend/src/components/study/StudyAnalysis.test.tsx`
- `webui/frontend/src/components/study/StudyAnalysis.tsx`
- `webui/frontend/src/lib/api.ts`
- `webui/frontend/src/lib/assessment-admission.test.tsx`
- `webui/frontend/src/lib/assessment-admission.ts`
- `webui/frontend/src/lib/evidence.ts`
- `webui/frontend/src/lib/geography/api.ts`
- `webui/frontend/src/lib/liftoff/api.ts`
- `webui/frontend/src/lib/physiology/api.ts`
- `webui/frontend/src/lib/simulation/api.ts`
- `webui/frontend/src/lib/station-fetch.test.ts`
- `webui/frontend/src/lib/station-fetch.ts`
- `webui/frontend/src/lib/study.ts`
- `.superpowers/sdd/2026-09-10-repeatable-study/task-6-report.md` (force-added task report).

The subsequent browser-fixture source snapshot was `final-source-5.json`, SHA256 `1f35ac1a0e41c10b4f04b19c2af4f502ee56a130a474a6d251700c66d332fc05`, 61 files. It adds only explicit researcher idle recovery at the existing preparation and registry browser fixtures after they intentionally leave measurement KSS. All 37 production files still match source2 byte-for-byte. This browser fixture correction was justified by actual initial browser output: 14 passed, one failed when the next language was correctly blocked by the prior unknown interrupted visit. Initial browser log `browser-final1.log` and its original `webui/frontend/test-results/study-preparation-measured-0201c--exact-PVT-return-in-es-419` screenshot/error context remain retained.

Additional changed browser fixtures:

- `webui/frontend/e2e/study-preparation.spec.ts`
- `webui/frontend/e2e/study-registry.spec.ts`

## Navigation interruption correction from the required shared browser group

The 38-case shared group exposed a real transport issue at the new explicit departure assertion: after full browser navigation, the previous fetch could be cancelled before recording unknown interruption. The station remained safely reserved (`uncertain:false` with the exact original lane); this was not accepted as a pass. Initial 24 cases passed, then measured-preparation English failed its uncertainty assertion. The already-failed run was stopped with SIGINT before source changes; its log `browser-final2.log` and unique `browser-final2-artifacts` retain the failure. No retry-only acceptance or relaxed assertion was used.

A focused RED in `navigation-red.log` recorded one failed, one passed test: the interruption request did not specify keepalive. `lib/assessments.ts` now uses fetch keepalive specifically for the bounded interruption POST, retaining exact attempt identity and unknown category across page departure. This does not claim that an unavailable network can deliver an interruption; the station still conservatively retains ownership until explicit recovery. The browser assertions still require an actual unknown interruption/uncertain reservation before named recovery.

Final source is `final-source-6.json`, SHA256 `dafc0a3c74f320211cdcbbfaad210fb7bd99eb93aea70a2758b617455c38e5c0`, 63 source/test files. The only new production file relative to source2 is the frontend assessment transport helper; all backend/native/scientific source bytes remain identical to the full backend/native/contracts/load passes. `format-navigation.log` and diff check preceded the final snapshot. Full frontend units/types/strict lint/build and the entire 38-case browser group were restarted on this source; their completion is recorded below.

Additional changed files:

- `webui/frontend/src/lib/assessments.ts`
- `webui/frontend/src/lib/assessments.test.ts`

## Completed final source6 verification

**DONE.** No Task6 blocker remains. Source6 verification checked all 63 source/test hashes with no mismatch (`final-source-verification.json`). The report is the 64th committed task file. No source mutation occurred during the final gates.

- `frontend-final3.log`: **271 tests, 81 files passed**, 99.08 s, including the exact keepalive regression. `typecheck-final3.log`, `lint-final3.log`, `build-final3.log`: exit0, zero lint warnings, successful production build.
- `browser-final3.log`: **38 passed in 2.9 minutes**, no retries. Entire required shared study/participant group plus station and saved-analysis workflow, on the rebuilt app. Actual English and Spanish full-navigation interruption/uncertainty/recovery assertions passed (22.4/23.3 s), and final registry boundary passed (6.2 s). The server was isolated at `.suas-e2e/277268/matb-e2e.db`; raw browser artifacts remain in unique `browser-final3-artifacts`.
- Backend: all 461 originally collected non-skipped tests are covered by the full run plus the successful targeted correction run; the later three route-matrix additions also pass (464 distinct backend cases covered across final runs). One existing full-suite skip. The new 15-case station module passes independently in both auto and core.
- Native: 854 passed. Scientific contracts: all 590 non-skipped cases passed across full plus corrected-environment run; nine existing skips. Documentation passed. Three software load scenarios completed without dropped samples/incomplete source closure.

Exact final frontend/browser command sequence (cwd `webui/frontend`, supported escalated execution):

```sh
npm test
npm run typecheck
npm run lint -- --max-warnings=0
npm run build
MATB_PYTHON=/root/repos/MATB/.venv/bin/python PYTHONPATH=/tmp/matb-predictability-testdeps PYTHONDONTWRITEBYTECODE=1 npx playwright test --config=playwright.config.ts --output=../../.test-tmp/repeatable-study/task6/browser-final3-artifacts e2e/station.spec.ts e2e/study-analysis.spec.ts e2e/study-registry.spec.ts e2e/study-preparation.spec.ts e2e/participant-journey.spec.ts e2e/frontend-predictability.spec.ts
```

Exact navigation RED command (cwd repository): `npm --prefix webui/frontend test -- src/lib/assessments.test.ts`, one failure/one pass in 1.39 s before keepalive. Initial station RED used the backend prefix above with `tests/test_station_resources.py` when that module contained the first three tests; all three failed because the implementation module did not exist. Subsequent GREEN source6 full-unit and source4 station profile results are retained above.

Legacy screenshot preservation: the existing registry fixture writes `/tmp/task3-assigned-pvt.png`. Its prior bytes were retained before that fixture ran as `prior-task3-assigned-pvt.png`; the final screenshot is retained as `assigned-pvt-final.png`, and the prior shared `/tmp` file was restored afterward. Earlier test basetemps, initial browser errors, proofs, zips and source manifests remain retained. Root restored its ten generated tracked Python cache files to HEAD; they are not in this task's changes.

Practical limits/handoff: load observations are software-only, not station/hardware qualification. Browser unavailable-network ownership remains conservative until researcher idle recovery. Existing multipart/SQLModel/statistical-library warnings and the separately retained Windows MEDIUM FIXTURE01 presentation flake belong to Task7's agreed cleanup/final all-suite/fail-on-flaky gate; this Task6 browser run has no flake/retry. The core export dry-run is provisional, and Task7 still owns final physical package inclusion/restore, warning cleanup and remote CI closure. Push/PR delivery remains with root.
