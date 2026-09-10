# Task 4 — measured preparation, exposure, and assigned participant flow

Worktree: `/root/repos/MATB/.worktrees/repeatable-study`; branch `codex/repeatable-study`.
Base: `f6a77850f7f270a57750e6c0b485b9b2b72376fc`. Implementer owns only Task 4; controller owns independent review, push and CI. No merge, push, scientific approval, physical qualification, or sibling-checkout modification was performed.

## Implementation and exact downstream contracts

Preparation is an append-only evidence layer attached to the existing immutable study version, exact assignment, occasion and actual practice attempts. It replaces the Task 3 `study_preparation_engine_pending` gate with `study_preparation_required`, and `preparation_gate='measured'`. Resource protection, scientific analysis and plan eligibility remain honestly pending for their later tasks.

`study_preparation` stores the exact assignment/participant/version/occasion, configuration hash, immutable requirement JSON, initial presentation JSON and identity hash. `study_preparation_event` retains demonstration, acknowledgement, each comprehension response (including wrong responses), measured practice decisions, explicit prior-practice reuse, native presentation/failure and preparation-stop events. `study_preparation_practice` prospectively links each exact practice attempt to its preparation; it never guesses historical practice membership. `study_native_preflight` retains the exact native session/attempt, reserved block UUID, original CSV path and resolved snapshot. SQLite UPDATE/DELETE triggers protect all five tables. Generic models and imports remain core-safe; native adapters load only inside their native operations.

The initial preparation presentation includes `preparation_implementation={version:'measured-preparation-v1', source_files:{relative_path:sha256}, sha256}`. Its concrete file inventory is `PREPARATION_SOURCES` in `app/study_preparation.py`: item generation/grading and its native observation/mapping adapters, typed criterion policy, preparation router, participant presentation component, native snapshot implementation and scientific evidence reconciliation/contract source. The full instrument `implementation_sha256`, authored config, locale, input mapping, enabled items, criterion IDs/rationales/comparators/thresholds and source inventory are retained together. This lets Tasks 5/7 explain an actual decision, rather than recovering only a pass label. Instrument source hashes also include the preparation integration and relevant participant copy; PVT's existing instruction/audio/scoring closure remains intact.

Browser items use the existing PVT SPACE/response-area mapping and the existing four-task screen controls. Native items derive from actually enabled task start events and resolved initial response parameters; disabled tasks contribute no items. Recognition is scored only against exact item IDs. Wrong responses are preserved; arbitrary extra/disabled items are rejected. Demonstration and acknowledgement remain administrative stages and cannot stand in for objective practice.

`begin_practice` creates an existing local `practice` occasion/attempt tied to that frozen preparation configuration. Existing unfinished practice is reopened by exact ID. Subsequent practice uses the same occasion with explicit `repeat_of` and reason; a finished practice must be graded before another is created. PVT/screen decisions read persisted `PracticeResult` raw input plus server scores, checking language and actual trial presence. PVT retains actual duration and the actual practice fast-mode/language/duration configuration separately from the full study binding. Native decisions read the exact suite/block's reconciled `EvidenceRun`, `EvidenceMetric` and `EvidenceRecord` sources; exported metric names `sysmon_hit_rate` / `track_rmse_deviation` map to authored policy names `sysmon.hit_rate` / `track.rmse_deviation`. Only succeeded numeric metrics can satisfy researcher-authored criteria. Capture participant/purpose/parent-suite/block identity must match. Conflicting successful derivation fingerprints block with review; failed or unavailable native practice/mapping produces retained failed exposure, never a fabricated pass. Pending derivation blocks grading until complete. Successful source payloads retain capture/run/fingerprint/metric IDs and the actual practice snapshot.

Explicit reuse is a researcher action selecting an exact original successful practice-event ID with actor and reason. Candidate preparation must have identical participant, frozen version, instrument, config, presentation language/implementation and authored practice criteria. The new event references the original preparation/event/attempt; it creates no second performed exposure or duration. Automatic cross-assignment reuse is disabled. Prescribed-later practice cannot be satisfied by this reuse action. Native stable mapping comparison removes only the generated own callsign and snapshot digest; enabled tasks, actual device capabilities and response mapping must still match. Actual assigned callsign comprehension is always separately retained for the new runtime.

Exposure GET returns participant/instrument/purpose/version/config/attempt IDs, repeat ordinal/parent, acquisition outcome, known times, trustworthy task duration and competence outcome. Unknown historical purpose, time, configuration and competence remain explicitly unknown. Administrative attempt creation time is not substituted for a missing historical acquisition time. Native practice duration uses scenario observations, never preflight wall time. Original purpose provenance and immutable historical occasion classification remain independently reviewable; retrospective classification is not analysis inclusion permission.

### Preparation/native ordering and Task 6 ownership

The supported sequence is: complete native practice → finish its derivation and grade → prepare the actual assigned native process while the shared study attempt is still `created` → bind that actual process's mapping/callsign and complete assigned recognition → baseline PVT → explicitly admitted release of that same native process/CSV/block identity. Backend preflight admission also enforces practice-before-held-runtime; this is not only a UI ordering convention. One native process owns the controller at a time. A practice runtime and an assigned held runtime are never launched together by this flow.

`CreateOpenMatbSession.preparation_only=true` requires an unstarted exact study assignment and its frozen preset/instruction/visual configuration. It produces `PREFLIGHT_READY`. `POST /openmatb/sessions/{id}/preflight` uses the existing controller lease and stdio bridge to launch with `MATB_PREPARATION_HOLD=1`, progressing `PREFLIGHT_STARTING → PREFLIGHT_HELD`. The native window remains hidden, scenario time does not advance, scheduled task events do not execute, and direct resume/event/plugin-start entry points cannot release the hold. Abort stays available. Snapshot resolution overlays initial scenario response parameters observationally, without modifying plugin parameters, callsign randomization, scoring, keys, geometry or timed stimuli. Future/dynamic response changes and unresolved generated mappings block with recovery. Required joystick axes/buttons/hats are observed and missing capabilities block; no mouse-control promise is invented.

The bridge `ready.preflight` snapshot uses schema `native-preflight-v1`, `enabled_tasks`, `mapping`, actual selected first pyglet controller name/capabilities, `issues` and SHA-256. The ordinary practice bridge also records its own real snapshot. Native run-specific callsign is resolved from the original process's existing CSV/session identity. A throwaway process is never substituted. Native presentation events preserve original instruction content/hash, actual enabled-task content, resolved controls, exact callsign, runtime snapshot, suite/attempt/CSV IDs and a hash of the actual resolved presentation. Failed snapshots are retained separately and require stopping/fixing the device or mapping before an explicit restart.

Held preflight reserves a block UUID but creates no acquired `OpenMatbBlockAttempt`, no task started timestamp, and no falsely started shared assessment. `StudyNativePreflight.created_at` and view `preflight_prepared_at` are the backend UTC snapshot-retention observation. On release, backend admission/prerequisite/preparation guards execute, the original reserved block is opened, and `release_preflight` carries the original snapshot digest. Native recomputes the snapshot, verifies it, records acquisition admission, shows the native window and acknowledges release. The view's `preflight_released_at` / `started_at` are the backend acknowledgement time, and `preflight_wall_duration_seconds` measures retained-ready to release-ack wall duration separately from acquired task duration. Native scientific `block.prepared` and `block.started` paired software timing observations retain the finer native monotonic preparation/admission boundary, including bootstrap time. The same CSV and process remain active. A missing acknowledgement is an interrupted/uncertain admission, terminates the owned process, and cannot be silently retried as a fresh start.

Preflight close/restart/abort retains its source and interrupted preparation state, does not produce completed acquired exposure, and remains recoverable through existing controller actions. Task 6 must distinguish `PREFLIGHT_*` from acquiring `STARTING/RUNNING/PAUSED/AWAITING_SCALE`; the held process still owns the native device while browser baseline runs. Opening the metadata log is not opening a measurement reservation. Native practice derivation/grade happens before that reservation. Finished native sessions are not whole-visit completion; participant completion explicitly asks the researcher to review and close visit collection.

Current supported limits are explicit before freeze: at most one required native held runtime before baseline in a visit; subsequent distinct run-specific recognition must be prescribed later. New native practice requiring derivation at `prescribed_later` is rejected because the current adapter cannot derive it inside a protected measurement visit. Bilingual authoring/validation directs the researcher to move native practice before baseline; later native recognition/comprehension and bounded browser practice remain supported. This is a software capability limit, not a scientific prohibition. Historic frozen records are readable and never rewritten.

### Scientific lifecycle compatibility

New derivations use `classic-evidence-1.1-preflight1`. Existing `classic-evidence-1.0` and `classic-evidence-1.1` are explicitly supported under their original direct-start lifecycle validation branch and preserve the requested version/fingerprint. Existing stored runs/results remain read-only on review/reopen. An explicit retry of a pending historical derivation uses that run's own stored version; a new requested derivation gets the current version. Existing offline verification passes the recorded version and analysis-execution provenance through reconciliation; it reports verifier-source differences separately instead of relabeling historic analysis.

For the new prepared-prefix branch, only one acquisition `block.started` is admitted. Before it, only zero-scenario-time bootstrap parameters, seed inputs/outputs, initial widget geometry/state, and an explicit list of native manual/provenance/visual metadata record types are accepted. Unknown records, input, performance, task lifecycle or scheduled events before admission fail reconciliation. Older genuine direct-start captures remain accepted. Scenario sample-gap logic and task calculators are unchanged; new native tests show a long held interval never enters scenario duration or measured update gaps, while real post-release stalls remain recorded.

### Endpoints and first-party routes

All preparation commands are under the existing protected local API:

- GET `/study/assignments/{assignment}/preparation`; POST `/study/assignments/{assignment}/preparation/{occasion_key}`.
- GET `/study/preparation/{id}`; POST `.../stages` with exact stage/item responses; POST `.../practice`; POST `.../grade` with exact practice attempt.
- POST `.../native-presentation` with exact held native session; GET `.../reusable-practice`; POST `.../reuse-practice` with event ID/actor/reason; POST `.../stop`.
- GET `/study/participants/{participant}/exposure`.
- Native prepared launch uses the existing create-session endpoint with `preparation_only`; leased `/preflight` holds, existing leased `/start` admits/releases, and existing abort remains available.

`/study/participant?assignment=...` shows the assigned version, one current scheduled assessment/preparation boundary, saved responses, explicit practice/reuse controls, help/stop, authored recovery waiting state, exact native release and exact-target ratings. It returns through `/pvt`, `/screen`, or `/openmatb/participant` without changing the task runners. Required preparation routes back to its exact assignment. Frozen occasion language controls participant copy independently of researcher language. Unresolved repeats/prerequisites/targets request exact researcher selection through existing assignment UI instead of guessing a latest attempt. The catalog remains available for standalone practice/exploration.

The assigned-attempt hook reacts to query changes, rejects mismatched response IDs and discards stale requests. PVT/screen visible selection changes with same-path assignment navigation while admitted/pending payload snapshots retain their original identity. Native questionnaire URLs include an exact questionnaire attempt, validated against the existing exact task target. Existing independent draft keys, target checks and append-only rating sidecars remain intact.

`/study/history?participant=...` shows exposure unknowns and the existing historical occasion/purpose classification APIs with immutable history. History responses are identity-bound. `StudyEditor` clears draft history on template load/clone/new identity and rejects stale asynchronous updates, repairing the Task 3 minor without changing immutable backend history. Common receipt facets add preparation (`unknown/required/prepared/not_required`) and plan eligibility (`pending`) while preserving existing raw-saving, processing, source, physical, human and protocol facets.

## TDD and verification record

Commands use the repository Python at `/root/repos/MATB/.venv/bin/python`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=/tmp/matb-predictability-testdeps`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `-B -m pytest -q -p no:cacheprovider`. Backend runs are from `webui/backend`, include `-p anyio.pytest_plugin` and explicit `MATB_COMPONENTS`; asynchronous/backend and browser gates use the controller-approved escalated context. Native runs are from `openmatb`; evidence runs are from repository root. No warnings were blanket-suppressed.

RED/GREEN evidence (full logs retained under `/tmp`):

- `/tmp/task4-backend-red.log`: 3 failures before the preparation module existed. `/tmp/task4-backend-green.log`: 17 passed (initial preparation plus registry coverage). Actual persisted PVT fixture trial fields were corrected to the existing input schema, without changing its validation.
- `/tmp/task4-native-red.log`: initial missing preflight/unsafe hold regression; `/tmp/task4-native-green.log`: 2 passed. Later `/tmp/task4-native-clock-red.log`: direct plugin `start` was called before admission (1 failed, 2 passed); `/tmp/task4-native-clock-green.log`: 3 passed after closing the entry guard.
- `/tmp/task4-native-admission-red.log`: logger did not yet support deferred scientific admission; `/tmp/task4-evidence-admission-red.log`: prepared prefix rejected as incomplete lifecycle. `/tmp/task4-native-admission-green.log`: 117 passed across preflight/logger/scheduler/controlbridge/clock; `/tmp/task4-evidence-admission-green.log`: 9 passed.
- `/tmp/task4-reuse-red.log`: missing explicit reuse implementation (1 failed, 6 deselected); `/tmp/task4-prep-next.log`: 7 passed after exact evidence reuse implementation. `/tmp/task4-native-observations.log`: 8 passed including real persisted/reconciled native practice, failed exposure and repeat.
- `/tmp/task4-history-red.log`: reproduced draft A history under saved template B (1 failed, 3 passed); `/tmp/task4-history-green.log`: 4 passed after identity/stale-response fix.
- `/tmp/task4-later-native-red.log`: unsupported later native practice did not raise before freeze. Initial green iteration exposed a fixture's hardcoded R01 visit ID colliding with the preceding native fixture; browser capability proof was separated into its own isolated test database rather than weakening identity assertions.
- Browser `/tmp/task4-browser-prep.log`: Spanish measured practice passed; English found frozen-language return-link leakage. The return link now resolves the attempt's frozen locale. `/tmp/task4-browser-prep2.log`: both actual EN/ES PVT preparation/return cases passed; native test's indexed `.all()` locators shifted as six confirmation buttons disappeared. A bounded diagnostic retained `/tmp/task4-browser-native-debug2/.../test-failed-1.png`; fixture now asserts six initial buttons, performs six first-remaining clicks, then asserts zero. Subsequent EN native exact-release/rating navigation passed in 3.7 seconds; Spanish fixture was corrected to the existing button text `Guardar escalas y continuar`. Neither fix changes task/rating behavior.
- Covering intermediate `/tmp/task4-backend-cover-final.log`: 89 passed/1 failed due to the existing legacy exact receipt dictionary lacking the two additive facets; all four original unknown facets remain asserted plus preparation unknown and plan eligibility pending.
- `/tmp/task4-backend-cover-auto.log`: 133 passed; `/tmp/task4-backend-cover-core.log`: 83 passed, 16 expected optional-component skips; `/tmp/task4-front-final.log`: 18 passed; `/tmp/task4-evidence-cover.log`: 16 passed. A subsequent auto iteration (`/tmp/task4-backend-final-auto.log`) correctly rejected a fixture freeze after the implementer changed hash-bound source during the run: 133 passed/1 failed, `study_validation_failed` / installed implementation changed. Final covering runs use frozen source; no guard was relaxed.
- Normal production build initially hit Turbopack's sandbox worker port restriction. Controller Python/Node loopback probes succeeded; the failed worker evaluation persisted in generated `.next`. Controller preserved that generated cache at `/tmp/matb-task4-next-portfail-cache`, then the clean ordinary `npm run build` succeeded under escalation (`/tmp/task4-build-controller-clean.log`). No webpack/framework/source workaround was used and there was no approval rejection. Intermediate TypeScript mistakes in the new recovery response interface were corrected before final gates.

Final covering command/output table is appended after all stable-source gates complete.

## Self-review and known boundaries

Self-review caught and fixed the direct native plugin-start bypass, false bootstrap `block.started`, old-version reconciliation allowlist, actual exported native metric-name mapping, failed native-practice retry dead end, exact suite/block capture verification, practice-before-preflight enforcement, stale assignment/error/history handling, frozen-language return link, questionnaire URL/target selection, release uncertainty and unsupported later-native-practice/resource deadlock. Source and original artifact identities remain intact. Scoring calculators, native task logic/randomization, keyboard shortcuts, geometry and browser timed-stimulus implementations were not changed.

Hardware/runtime transport fixtures are explicitly software-only. They establish API, persisted observation, scheduler and UI contracts, not physical controller/audio/display qualification or human calibration. No universal competence threshold or empirical scientific approval was supplied. Authored thresholds in tests are fixture-specific workflow checks.

Task 5 must consume original practice decision sources plus native presentation/prepared/acquired distinctions. Task 6 owns whole-visit measurement reservations and heavy-work deferral, using the timing/ownership boundary above. Task 7 must preserve the preparation source inventory, original instruction content, actual native snapshots, CSV identity and exact evidence/rating artifacts, including old pinned derivation versions. Completion of a native task is intentionally not collection-close or analysis inclusion.

## Final admission follow-up and browser diagnosis

The final self-review/controller gate identified that a prior successful native preparation could admit a newly generated ordinary native runtime. `study_preflight.require_held_launch` now rejects normal assigned create and persisted READY/BETWEEN_BLOCKS start whenever that exact native occasion prescribes any demonstration, acknowledgement, comprehension or practice. It returns HTTP 409 `study_native_preflight_required` with a bilingual recovery message and exact `/study/participant?assignment=...` URL. The only prepared-study release route validates the retained same-session snapshot/presentation. Explicit no-preparation frozen native protocols, standalone practice, historical reads and abort/recovery retain their prior behavior.

`tests/test_study_preparation.py -k native_preflight` RED (`/tmp/task4-bypass-red.log`): 2 failed, 10 deselected; normal create reached acquisition-source creation and persisted ordinary start reached unheld subprocess launch. GREEN (`/tmp/task4-bypass-green.log`): 2 passed, 10 deselected. The create fixture was then strengthened to a genuinely new explicit repeated attempt after prior matching preparation and a completed prior native source, preserving the ordinary acquisition API and repeat policy; `/tmp/task4-bypass-exact-green.log`: 2 passed, 10 deselected. Both parametrized paths also complete the original exact held release and verify unchanged CSV/block identity. The persisted READY state is an explicit software fixture for an older ordinary source, not a physical runtime claim.

Browser intermediate `/tmp/task4-browser-matrix-final.log`: 20 passed, 1 failed, 7 did not run. The legacy journey expected five generic stages after the current workflow had four; the updated fixture asserts all four actual named stages (and retains actual PVT/KSS/stimulus completion). Its extra outside-test error is Playwright's max-failures stop reporter, not an application exception. `/tmp/task4-browser-acceptance.log`: 6 passed (journey, measured PVT preparation, exact native/rating navigation in both languages), 1 failed, 1 did not run; the historical select's nested label includes option text for exact label matching. The accessibility snapshot already showed the exact named `combobox`; using that semantic role fixed the locator while retaining the full stale-response and immutable classification assertions. Focused `/tmp/task4-history-browser-green.log`: 1 passed in 3.2 seconds. Earlier interrupted native ES/history cases were never counted as passes; the full final matrix below supersedes these partial/interrupted iterations.

## Source and artifact inventory

Changed/new Task4 source and tests (paths relative to this worktree; generated dependency/build/test artifacts are excluded):

- `.github/workflows/matb-ci.yml`
- `matb_integration/evidence/contracts.py`
- `matb_integration/evidence/reconcile.py`
- `openmatb/core/logger.py`
- `openmatb/core/preflight.py`
- `openmatb/core/scheduler.py`
- `openmatb/tests/test_preflight.py`
- `tests/test_evidence_pipeline.py`
- `tests/test_evidence_provenance.py`
- `webui/backend/app/assessment_adapters.py`
- `webui/backend/app/assessment_service.py`
- `webui/backend/app/evidence_service.py`
- `webui/backend/app/main.py`
- `webui/backend/app/openmatb_records.py`
- `webui/backend/app/openmatb_runtime.py`
- `webui/backend/app/openmatb_schemas.py`
- `webui/backend/app/routers/openmatb.py`
- `webui/backend/app/routers/study_preparation.py`
- `webui/backend/app/study_admission.py`
- `webui/backend/app/study_bindings.py`
- `webui/backend/app/study_native.py`
- `webui/backend/app/study_native_practice.py`
- `webui/backend/app/study_policies.py`
- `webui/backend/app/study_preflight.py`
- `webui/backend/app/study_preparation.py`
- `webui/backend/app/study_registry_models.py`
- `webui/backend/tests/test_openmatb_records.py`
- `webui/backend/tests/test_study_acquisition.py`
- `webui/backend/tests/test_study_preparation.py`
- `webui/backend/tests/test_study_registry.py`
- `webui/frontend/e2e/participant-journey.spec.ts`
- `webui/frontend/e2e/study-fixtures.ts`
- `webui/frontend/e2e/study-preparation.spec.ts`
- `webui/frontend/src/app/openmatb/participant/page.tsx`
- `webui/frontend/src/app/openmatb/session/page.tsx`
- `webui/frontend/src/app/openmatb/setup/page.tsx`
- `webui/frontend/src/app/pvt/page.tsx`
- `webui/frontend/src/app/screen/page.tsx`
- `webui/frontend/src/app/study/history/page.tsx`
- `webui/frontend/src/app/study/participant/page.tsx`
- `webui/frontend/src/components/assessments/AssessmentPages.test.tsx`
- `webui/frontend/src/components/assessments/AssessmentPicker.tsx`
- `webui/frontend/src/components/openmatb/AssignedWorkloadQuestionnaire.test.tsx`
- `webui/frontend/src/components/openmatb/AssignedWorkloadQuestionnaire.tsx`
- `webui/frontend/src/components/study/PolicyEditor.tsx`
- `webui/frontend/src/components/study/StudyAssignments.tsx`
- `webui/frontend/src/components/study/StudyEditor.test.tsx`
- `webui/frontend/src/components/study/StudyEditor.tsx`
- `webui/frontend/src/components/study/StudyHistory.tsx`
- `webui/frontend/src/components/study/StudyParticipant.tsx`
- `webui/frontend/src/components/study/StudyReturn.tsx`
- `webui/frontend/src/lib/assessments.ts`
- `webui/frontend/src/lib/assigned-attempt.test.tsx`
- `webui/frontend/src/lib/assigned-attempt.ts`
- `webui/frontend/src/lib/openmatb/api.ts`
- `webui/frontend/src/lib/openmatb/progress.ts`
- `webui/frontend/src/lib/study.ts`
- `webui/frontend/src/types/openmatb.ts`

The report itself is force-added from the ignored `.superpowers/sdd/2026-09-10-repeatable-study/task-4-report.md` directory. No generated `.next`, `.suas-e2e`, database, CSV, screenshots, test logs, Python cache or dependency directory is committed.

Persisted runtime artifacts remain under the existing controlled suite root: published visual-profile snapshot; per-assigned-occasion generated scenario; original native CSV and scientific sidecars under `sessions/{occasion_or_practice_key}`; block/capture/reconciled-run/metric identities in the database; original compatibility rating sidecar and immutable `scales/ratings/{questionnaire_attempt_id}.json`. New preparation records reference those originals. No replacement export format is introduced. The five new immutable tables and their JSON source snapshots must be included by Task7's restore/export closure. Software browser artifacts/logs live under `/tmp/task4-*`; final matrix artifacts are `/tmp/task4-delivery-browser` and final command logs use `/tmp/task4-delivery-*.log`.

Exact preparation implementation file inventory at final source freeze (the runtime also stores these hashes, their canonical digest, and `measured-preparation-v1`):

| Source | SHA-256 |
| --- | --- |
| `webui/backend/app/study_preparation.py` | `18aa170c299984b9711a088103d0cc4ed50742e64d275f8e3f300f6394f9f501` |
| `webui/backend/app/study_preflight.py` | `f742dd768b28317c58e71378347c6c4b690469c699c8d075a0ae1db7bf429427` |
| `webui/backend/app/study_native_practice.py` | `8ce93c0345fed978995965d68793b9082d0b207db8748249d0c577465e64e78d` |
| `webui/backend/app/study_policies.py` | `4d8c31b37e076864fd1166b3c087adee769898367d7ace5d6c52d366d94edc83` |
| `webui/backend/app/routers/study_preparation.py` | `347bd72184969eb5f5c2910e29f8ec5b265238dc4b37328a2db385f9b5beb514` |
| `webui/backend/app/assessment_service.py` | `bbfe3848e02fa00fcfd3b76d3b70dd64ca81a0cb58a825e453ddf2e174311aef` |
| `webui/backend/app/study_admission.py` | `2b98ce7f2af0601855cd3fbd87904c5a3573c7dbb23dfa28460ad53606344977` |
| `webui/frontend/src/components/study/StudyParticipant.tsx` | `a9c902bc905dfacf8c43d573f8fb5630db7fc5ebcef344b113a430aa9d50a510` |
| `openmatb/core/preflight.py` | `cc670fb0d522648afadd2a984739311dbbc1f57275c2b2c188ef0aab66075b1f` |
| `matb_integration/evidence/reconcile.py` | `389531074ef0eff51f73c26a607483bc4128002bd19ce55639ebd3f2dd5374c5` |
| `matb_integration/evidence/contracts.py` | `637aa3ef4213b7febfa9e0a87c61ff5ef46c0256be0d99f0393e61c4502dc7ef` |

## Final admission and durable-stop completion

`study_preparation_admission` is the fifth new immutable table: `attempt_id` PK/FK, `assignment_id` FK, `snapshot_json`, `snapshot_sha256`, `created_at`. It is written only during the locked `created → started` measurement transition, in the same database transaction as acquisition start, after guards succeed. `preparation-admission-v1` records exact attempt/assignment/version/study/config identities and the selected requirement evidence. Each entry includes `preparation_id`, immutable presentation/criterion identity and config hash, accepted `decision_event_ids`, and an immutable `event_frontier` (event ID, stage, pass, practice attempt, exact payload SHA-256 and timestamp). Thus native presentation and all actual practice decision sources are fixed at admission, including prior failures, without copying or rewriting originals.

Native release selects the preparation belonging to that exact native source session; another matching ready runtime cannot satisfy it. The generic assessment-start route cannot admit a native occasion requiring preparation; only the internally validated held-source release can do so. Explicitly no-preparation native protocols retain their existing path. Failed admission creates no admission snapshot. GET attempt adds `preparation_admission` (typed in the frontend); historic measurements have null and preparation receipt unknown, never a retrospectively invented binding. Admitted receipts use the immutable admission; current readiness remains independently queryable. Task5 must use this snapshot/frontier for the actual measurement, rather than reselecting a currently ready preparation. Task7 must preserve this fifth table and original referenced rows.

`tests/test_study_preparation.py -k measurement_admission` RED `/tmp/task4-admission-binding-red.log`: missing model, 1 failed/12 deselected. GREEN `/tmp/task4-admission-binding-green.log`: all 13 preparation tests passed. The test obtains real persisted practice observations, admits a measurement, stops/restarts preparation with new successful practice under an explicitly prescribed-later policy, then verifies the original admission bytes/hash/frontier remain unchanged, its receipt remains prepared, and UPDATE is rejected. Native exact-session frontier assertions accompany retained-process release. Additional generic native-start RED `/tmp/task4-native-direct-admission-red.log`: 2 failures because direct starts did not reject; `/tmp/task4-preparation-final-green.log`: 13 passed after restricting admission to actual release. Source selection is atomic under the existing registry lock; idempotent starts do not backfill historical or replace existing snapshots.

The stop UI now calls the durable stop endpoint before displaying success. It first obtains/aborts the actual native runtime; an unconfirmed abort leaves preparation visibly unresolved. A confirmed native abort followed by a failed stop write shows the write error; retry observes ABORTED and retries persistence without claiming a second physical abort. A stopped preparation cannot resume through Continue; explicit restart creates a separate row and retains original answers/exposure. The stage label is localized. Existing timed task stop mechanisms are unchanged.

Keyboard-stop RED `/tmp/task4-stop-browser-red.log`: displayed stopped while the API still reported demonstration (1 failed). EN/ES native stop-failure cases cover abort uncertainty, failure to save the stop event, retry and original native presentation retention. Intermediate test-only diagnostics found asynchronous request observation and Next's separate route-announcer alert; assertions now wait for exact request milestones and exact failure text. `/tmp/task4-stop-native-green3.log`: 2 passed. The full final browser matrix adds those two tests (30 total) and extends both actual measured-PVT cases with keyboard stop → persisted event → reload → explicit restart → preserved original stopped event → newly measured practice.

Before this final batch, `/tmp/task4-delivery-*` covering checks passed: auto 153; core 90/18 expected skips; native 119; evidence 16; frontend 18; lint/typecheck/build exit 0; complete browser matrix 28 passed. Those are valid intermediate evidence, not claims for later edits. No native scheduler/logger or evidence reconciliation source changed after the 119/16-pass covering runs, so those checks remain applicable; all affected backend/frontend/browser gates are repeated below.

## Final stable-source covering gates

Source was frozen after the completed brief/spec cross-check and batched admission/stop fixes. Python commands use the environment/prefix documented above; exact test selections follow. Every listed final result was checked after process completion; no gate remains pending.

| Gate | Exact selection/command | Result/log |
| --- | --- | --- |
| Backend auto | `tests/test_study_preparation.py tests/test_study_registry.py tests/test_study_acquisition.py tests/test_assessments.py tests/test_assessment_review_fixes.py tests/test_purpose_provenance.py tests/test_study_protocol.py tests/test_openmatb_runtime.py tests/test_openmatb_records.py tests/test_evidence.py tests/test_evidence_review.py` | 154 passed, 1 existing warning, exit 0 — `/tmp/task4-final2-backend-auto.log` |
| Backend core | same first seven files, through `test_study_protocol.py`, with `MATB_COMPONENTS=core` | 91 passed, 18 expected optional-component skips, 1 existing warning, exit 0 — `/tmp/task4-final2-backend-core.log` |
| Native | `tests/test_preflight.py tests/test_logger.py tests/test_scheduler_logic.py tests/test_controlbridge.py tests/test_clock.py` | 119 passed, exit 0 — `/tmp/task4-delivery-native.log` (native source unchanged afterward) |
| Evidence/old derivation | `tests/test_evidence_pipeline.py tests/test_evidence_provenance.py` | 16 passed, exit 0 — `/tmp/task4-delivery-evidence.log` (derivation source unchanged afterward) |
| Frontend units | `npm test -- src/components/study/StudyEditor.test.tsx src/components/study/PolicyEditor.test.tsx src/lib/assigned-attempt.test.tsx src/components/assessments/AssessmentPages.test.tsx src/components/openmatb/AssignedWorkloadQuestionnaire.test.tsx src/app/openmatb/setup/page.test.tsx` | 6 files / 18 tests passed, exit 0 — `/tmp/task4-final2-frontend.log` |
| Lint | `npm run lint` | exit 0, no findings — `/tmp/task4-final2-lint.log` |
| TypeScript | `npm run typecheck` | exit 0 — `/tmp/task4-final2-typecheck.log` |
| Production | `npm run build` (standard Next/Turbopack, escalated) | exit 0 — `/tmp/task4-final2-build.log` |
| Browser complete CI selection | `MATB_PYTHON=/root/repos/MATB/.venv/bin/python PYTHONPATH=/tmp/matb-predictability-testdeps MATB_COMPONENTS=auto PW_TEST_MATCH='**/{study-registry,study-preparation,participant-journey,frontend-predictability}.spec.ts' npm run test:e2e -- --retries=0 --max-failures=1 --output=/tmp/task4-final2-browser` | 30 passed, no retries, exit 0 (2.6 minutes) — `/tmp/task4-final2-browser.log` |

Task4 source and this report are committed together after all covering gates passed, from base `f6a77850f7f270a57750e6c0b485b9b2b72376fc`; the resulting full SHA is provided in the implementer handoff. Root performs the fresh independent task gate and committed stripped-core startup smoke; no worker reviewer was spawned. No push or merge was performed.


Final self-review: all Task4 brief boundaries were cross-checked before the last source freeze. Measured stages, failed/repeated actual practice, mapping/enabled-task and version identity, immutable per-admission decisions, assigned routing, historical unknowns/classifications, exact questionnaire selection, language, keyboard help/stop and source-safe legacy compatibility are covered. `git diff --check` is clean. The eleven preparation implementation source hashes above were independently recomputed and match the final files. Remaining limits are the explicit native scheduling/derivation capabilities and deferred Tasks5–7 responsibilities already described; there is no claim of physical qualification or complete whole-visit analysis/backup implementation in Task4.
