# Task 2 implementation report

Status: implemented and verified; ready for independent review. All changes are in
`/root/repos/MATB/.worktrees/repeatable-study`, branch `codex/repeatable-study`.
No push/merge, production migration, sibling worktree changes, or subagents.
The separate foundation CI harness fix is commit
`6bba6aa59622c4057f0bead04297d6ae43a9762d`, documented in
`ci-foundation-fix-report.md`; root independently verified/pushed that fix.

## Implementation

- Added instrument-neutral UUID occasions, ordinal UUID attempts, immutable source
  links, and named append-only retrospective occasion classifications. An explicit
  occasion requires an existing participant's real assigned Visit. Instrument,
  phase, order, condition, optional version reference, origin, collection group and
  accompanying occasion are retained. No frozen protocol versions are fabricated.
- New attempt creation declares prospective purpose immediately through Task1's
  immutable ledger, before acquisition starts. The eventual PVT/screen result or
  bound optional source reuses that same UUID and does not append another declaration.
- Attempts retain repeat-of/reason, exact questionnaire target, interruption category,
  state and independent timestamps. Repeat requires a finished/interrupted/unknown
  prior attempt and no active attempt in that occasion. Unknown historical context
  cannot be reused to acquire a new study result; create a real assigned occasion.
- A questionnaire must name an exact non-questionnaire target in the same participant
  visit. Accompanying physiology requires the same participant, visit and explicit
  collection group as its named occasion. A four-task screen is one acquisition.
- PVT and screen persistence now keys uniqueness by attempt identity. The deprecated
  overwrite parameter cannot delete or replace an acquisition: differing content
  returns409 with an actionable explicit-repeat response. Identical final retries
  return the original source ID; conflicting content for the same attempt returns409.
  Acquisition finish and raw save are independent: a finished acquisition may still
  save its first raw result; raw-save receipts remain unknown until it does.
- PVT/screen explicit attempts can repeat within a visit without overwriting old
  trials, scores, source IDs, archived snapshots or purpose identities. Practice
  remains in PracticeResult and has the same explicit attempt/idempotence support.
- Added source adapters for PVT/screen/practice/archive, native suite/block/rating,
  mission/technical session/block, Liftoff, H10 and paired-v3 EvidenceCapture.
  These adapters query installed tables and never import optional runtime modules.
  Native and mission practice blocks receive their own actual practice declarations,
  rather than inheriting the surrounding study suite's purpose. Native questionnaire
  source links bind the exact shared native task attempt.
- Imported external/orphan evidence captures receive unknown purpose provenance at
  import/migration time, with actor system:migration. Their original capture IDs,
  manifest text, hashes and artifact streams remain unchanged. A console-owned
  capture joins the native attempt only when the original block identity, parent
  session and actual purpose match. Existing inspectors and capture exports remain
  operational; evidence discovery and native receipts expose additive shared IDs.
- Common receipts keep raw saving, acquisition, ratings and processing separate.
  Source adapters expose recorded native/H10/session state without converting an
  acquisition completion into a rating, processing or scientific eligibility claim.
  Unknown historical receipt facts remain unknown. Original artifact/raw endpoints
  remain authoritative for optional instruments.
- Journey and prerequisite readers now accept explicit selections or reject ambiguous
  repeated observations. PVT list exposes every study attempt and labels that mode.
  Legacy screen cohorts reject duplicates instead of selecting arbitrary participant
  rows. Known nonstudy ledger classifications are excluded even when the preserved
  original source execution_purpose still says study. Ambiguous legacy fit refresh
  returns0 without modifying existing fits; an already-saved repeat is not reported
  as an HTTP save failure. The legacy CSV Block table is unchanged.
- Added shared first-party EN/ES occasion/attempt/history controls to PVT and screen:
  researcher-defined phase/order, assigned visit, independent reopening of exact raw
  evidence, interruption recording, and reasoned repeats. Removed PVT visit-level
  completion blocking and automatic overwrite. The parent awaits server start before
  entering KSS or mounting the screen battery; PvtRunner stimulus timing is unchanged.
  Added a guard against selecting an old attempt after a pending preparation resolves
  following a participant/visit context change. Read frontend AGENTS.md and installed
  Next use-client.md before editing frontend code.

## Concrete contracts for Tasks 3–7

Models in `app.assessment_models`:

- `AssessmentOccasion` / `assessment_occasion`: UUID id; nullable original
  participant_id/visit_id for legacy context; instrument; nullable historical
  phase/order/condition/version_ref; origin; collection_group_id;
  accompanying_occasion_id. SQL UPDATE/DELETE rejected.
- `AssessmentAttempt` / `assessment_attempt`: UUID id; occasion_id; ordinal;
  purpose_provenance_id; execution_purpose; repeat_of/repeat_reason;
  target_attempt_id; interruption_category; acquisition_state;
  created_at/started_at/finished_at; final_payload_sha256;
  raw_saving/ratings/processing. Unique(occasion_id, ordinal).
- `AssessmentSourceLink` / `assessment_source_link`: UUID id; attempt_id;
  source_table; source_id as text; role (acquisition or ratings);
  purpose_provenance_id. Unique(source_table, source_id, role), SQL immutable.
  Use the archive's own ID for source_table=archived_assessment, never its original_id.
- `AssessmentOccasionClassification`: append-only id, occasion_id, reviewed
  visit_id/phase/order/condition/version_ref, named reviewer/reason/references,
  actual recorded_at. Original unknown occasion fields are never rewritten.
  Later eligibility must require plan permission and inspect this history, separately
  from Task1 purpose history. A classification does not attest scientific approval.

HTTP routes (existing Host/Origin/bearer protection applies):

- POST `/assessments/occasions` ->201 occasion. Required participant_id, visit_id,
  instrument, phase, order>=1; optional condition, version_ref, collection_group_id,
  accompanying_occasion_id. Public origin is local. Supported instruments: pvt,
  screen, openmatb, liftoff, suas, physiology, questionnaire.
- GET `/assessments/occasions?participant_id=&visit_id=&instrument=` -> list.
  GET `/assessments/occasions/{id}` -> original occasion.
- POST `/assessments/occasions/{id}/attempts` ->201 attempt view. Body
  `{execution_purpose: study|practice, target_attempt_id?: UUID}`. Questionnaire
  target required. Cannot silently create a second attempt on the same occasion.
- GET `/assessments/occasions/{id}/attempts` -> ordinal-ordered attempt views.
  GET `/assessments/attempts/{id}` -> single view.
- POST `/assessments/attempts/{id}/start` and `/finish`: no body, idempotent same
  transition, return attempt view. State flow created->started->finished; interruption
  permitted from created or started, then an explicit repeat creates a new identity.
- POST `/assessments/attempts/{id}/interrupt` body `{category}`. Categories:
  operator_stop, participant_stop, technical_failure, lost_connection, other.
- POST `/assessments/attempts/{id}/repeat` ->201 new attempt; body execution_purpose,
  nonblank reason, optional target_attempt_id. Prior identity remains available.
- GET `/assessments/attempts/{id}/raw` -> `{attempt, records:[{link,record}], record}`.
  `record` is the first linked original source row (convenience for single-source
  PVT/screen); consumers of multi-source native attempts must use `records`/roles.
  PVT raw_trials_json and screen raw_trials_json are original stored strings.
  ArchivedAssessment exposes its unchanged snapshot_json and original_id.
- GET `/assessments/sources/{source_table}/{source_id}?role=acquisition|ratings`
  -> exact shared attempt. This is the universal source-instance lookup for Liftoff,
  mission, H10 and other existing instrument views, without rewriting their manifests.
- GET/POST `/assessments/occasions/{id}/classifications`: POST requires visit_id,
  phase, order, reviewer, reason; optional condition/version_ref/supporting_references.
  Only historical/legacy compatibility occasions; named non-system reviewer required;
  reviewed visit must belong to the original participant. Response contains original
  occasion_id plus append-only history/current. No prospective upgrade is possible.
- POST `/pvt`: existing scoring payload + optional attempt_id. POST `/screen`:
  existing participant_id/payload/execution_purpose + optional attempt_id. A prepared
  explicit attempt must match instrument/participant/visit where applicable/purpose
  and be started (or independently finished pending its first raw save).
- Final-content conflict:409 `code=final_payload_conflict`, attempt_id, repeat_url.
  Legacy overwrite/repeat ambiguity:409 `code=explicit_repeat_required`, message,
  attempt_ids. Ambiguous readers:409 `code=explicit_assessment_selection_required`.
- Journey accepts attempt_id for the selected instrument and pvt_attempt_id for a
  separately selected PVT prerequisite. Native/mission/Liftoff/H10 selections resolve
  through source links. Unselected multiple instances are refused.
- `require_study_pvt(db,visit_id,*,attempt_id=None)` selects explicitly or rejects
  ambiguity; invalid/legacy timing and known nonstudy classifications cannot qualify.
  `require_task_order(...,source_session_id=None)` accepts an exact prerequisite
  session; ambiguous native/Liftoff alternatives require selection. The legacy CSV
  Block pathway remains unchanged and must not be used to collapse native repeats.

Internal functions and lifecycle integration:

- `assessment_service.create_occasion/create_attempt/transition/save_result` do not
  commit; callers own transactions. `prepare_result` validates context and immutable
  final hash; `save_result` persists source, same purpose UUID, link and receipt
  atomically. `get_attempt/attempt_view/raw_view/occasion_history` expose identities.
- Task1 `declare_acquisition(db,row,*,purpose,attempt_id=None)` remains backward
  compatible. With attempt_id, it requires a transient supported source, binds that
  exact prepared attempt via `bind_new_source`, reuses its UUID and adds no declaration.
  Instrument, participant, available visit and purpose must match; an already-linked
  acquisition cannot be rebound. Optional runtime admission in Tasks3/4/6 should pass
  the chosen attempt through this hook. Source preparation does not fabricate raw,
  rating or processing completion.
- Existing endpoint calls without a prepared shared attempt are explicitly labeled
  `origin=legacy_compat`; associations preserve only recorded context (including null
  unknown H10/technical context), and do not invent study assignments or frozen versions.
  Explicit new occasion creation always requires a real visit. Tasks3/4 must gate
  modern study launch and pass the chosen attempt to the hook instead of interpreting
  compatibility association metadata as an assigned study occasion. This is the
  deliberate staged integration boundary in the Task2 brief, not an approval claim.
- `assessment_adapters.attach_source(db,table,source,historical=True)` is additive,
  idempotent by actual source table/ID/role. Historical imports use unknown ledger
  events when no source UUID exists. It must never be called with historical=False
  to relabel an already-acquired capture. `source_attempt`, `source_identity` and
  `receipt_facets` are the installed-table-safe read adapters.
- Source table map: pvt_assessment, screenresult, practiceresult,
  archived_assessment, openmatb_suite_session, openmatb_block_attempt,
  liftoff_session, simulation_session, technical_simulation_session,
  simulation_block, technical_simulation_block, polar_capture, evidence_capture.
- Receipt object keys: raw_saving, acquisition, ratings, processing. Native adapters
  retain original source status vocabulary; generic acquisition_state uses created,
  started, finished, interrupted, unknown. Do not equate these facets with qualification.
- Frontend `lib/assessments.ts` exports typed occasion/attempt CRUD, repeat/start/
  interrupt/raw functions. `AssessmentPicker` supports exact selection/reopening;
  its parent must await admission before starting actual acquisition. Task6 should
  extend this boundary with live-visit protection. No stimulus-time prompts were added.

## Migration evidence

`assessment_migration.migrate_assessments(engine)` is called by init_db after Task1
purpose migration. It issues explicit BEGIN IMMEDIATE so sqlite3's legacy DDL
transaction behavior cannot commit half a rebuild. It creates shared tables/triggers,
removes only old visit/participant uniqueness, adds nullable unique attempt foreign
keys on PVT/screen/practice, copies all original columns unchanged, associates source
instances, checks foreign keys, and commits once. Failure rolls back DDL and data.

The isolated migration regression uses real legacy SQL schemas with PVT ID42,
visit7, exact raw string ` [1,  2] `, screen ID9 with exact raw ` { } `, archive ID5
whose original_id is42 and whose snapshot contains original trial text. It asserts
all source IDs/raw/UUIDs/snapshot bytes remain identical, historical screen visit and
phase stay NULL, Block DDL is byte-identical, and link UUIDs remain identical after
rerun. A second PVT source in visit7 is insertable after migration. Injected failure
on INSERT INTO assessment_source_link proves the complete sqlite_master table schema
returns to its original form; retry then succeeds. No production dataset was touched.

## Exact test commands and results

Backend command prefix, cwd webui/backend, executed with async worker support:

```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/matb-predictability-testdeps PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 MATB_COMPONENTS=auto /root/repos/MATB/.venv/bin/python -B -m pytest -q -p no:cacheprovider -p anyio.pytest_plugin
```

RED suffixes (before each corresponding implementation):

- `tests/test_assessments.py`: 4 failed, 1 warning in0.48s; missing occasion endpoints.
  /tmp/task2-red.log. Initial fixture path/visit-lookup authoring errors were corrected
  before this valid four-404 RED run; no implementation was added to satisfy those errors.
- `tests/test_assessments.py -k migration`: 1 failed,4 deselected in0.21s;
  missing migration module. /tmp/task2-migration-red.log.
- `tests/test_assessments.py tests/test_openmatb_records.py -k 'new_legacy_adapter or journey_rejects or shared_native'`:
  3 failed,23 deselected in0.69s. /tmp/task2-adapters-red.log.
- `tests/test_assessments.py -k 'refresh_ambiguous or known_practice'`:
  2 failed,7 deselected in0.44s. /tmp/task2-cohort-red.log.
- `tests/test_assessments.py -k 'raw_save_can or questionnaire_cannot'`:
  1 failed,1 passed,9 deselected in0.41s. /tmp/task2-finish-red.log.
- `tests/test_assessments.py -k historical_occasion_review`:
  1 failed,11 deselected in0.30s. /tmp/task2-history-red.log.
- `tests/test_simulation_runtime.py -k mission_block_sources`:
  1 failed,18 deselected in0.50s. /tmp/task2-mission-red.log.
- `tests/test_assessments.py -k optional_source`:
  1 failed,12 deselected in0.28s. /tmp/task2-bind-red.log.
- `tests/test_evidence.py -k imported_capture`:
  1 failed,8 deselected in0.46s. /tmp/task2-evidence-red.log.

GREEN broad command, same prefix +:

```
tests/test_assessments.py tests/test_purpose_provenance.py tests/test_db_migrations.py
tests/test_pvt_endpoint.py tests/test_screen_endpoint.py tests/test_openmatb_runtime.py
tests/test_openmatb_records.py tests/test_liftoff_endpoints.py tests/test_physiology_api.py
tests/test_physiology_runtime.py tests/test_simulation_endpoints.py
tests/test_simulation_runtime.py tests/test_experiment_safety.py tests/test_hcf_refresh.py
```

171 passed,1 warning in57.90s (/tmp/task2-broad-final.log).
Earlier broad run:165 passed/1 failed because the old safety test expected destructive
archive replacement; it now verifies refusal and both independent retained source rows.
Earlier focused adapter run:26 passed (/tmp/task2-adapters-green.log); later changed-path
run:65 passed (/tmp/task2-final-focused.log). Counts overlap.

Post-broad external/native evidence changes, prefix +
`tests/test_assessments.py tests/test_evidence.py tests/test_evidence_review.py tests/test_openmatb_records.py`:
43 passed,1 warning in16.59s (/tmp/task2-evidence-green.log).

Final backend source state, same prefix with MATB_COMPONENTS=core +
`tests/test_assessments.py tests/test_db_migrations.py tests/test_evidence.py tests/test_evidence_review.py tests/test_openmatb_records.py`:
56 passed,1 warning in11.96s (/tmp/task2-last-core.log).
All backend warnings are the existing python_multipart pending deprecation.

Core smoke (cwd backend):

```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/matb-predictability-testdeps:. MATB_COMPONENTS=core MATB_DB_PATH=/tmp/task2-core-final.sqlite /root/repos/MATB/.venv/bin/python -B /tmp/task2-core-smoke.py
```

PASS: core startup twice, shared APIs present, optional runtimes not imported
(/tmp/task2-core-smoke.log). The script imports app.main, runs init_db twice,
asserts shared occasion/raw and purpose routes, and checks optional runtime modules
are absent from sys.modules.

Frontend cwd webui/frontend:

```
npm run typecheck
npm test -- src/components/assessments/AssessmentPicker.test.tsx src/lib/assessments.test.ts src/lib/api.test.ts src/lib/pvt.test.ts src/lib/screen.test.ts
```

Typecheck passed (/tmp/task2-typecheck-final.log).
32 tests passed/5 files,6.95s (/tmp/task2-front-covering.log).
Initial API RED: missing assessments module (/tmp/task2-front-red.log).
Self-review RED: `npm test -- src/components/assessments/AssessmentPicker.test.tsx`
yielded1 failed/1 passed for selecting an old context after pending creation resolved
(/tmp/task2-front-race-red.log); fixed with context invalidation and included in final
32-test GREEN. Raw reopening and reasoned repeat are tested through the real component
and HTTP adapter, with controlled transport responses.

`git diff --check` passed. No browser E2E was run; actual optional hardware acquisition
and physical timing qualification remain outside this source-level verification.

## Self-review and remaining integration boundaries

No unresolved implementation blocker. The core APIs, repeated PVT/screens, raw/ID
migration, historical classification and installed-source association contracts are
implemented and covered. Follow-on study assignment approval, analysis plan eligibility,
heavy-work admission and study-first navigation remain Tasks3–7 as specified.

- Preserve origin/unknown classification, actual reviewer identity and full history;
  never turn compatibility context or system inference into scientific approval.
- Callers must choose exact instances. Source-specific raw artifacts and derivation
  run selection remain in the existing inspector/export APIs; legacy CSV tables must
  not absorb new native repeats. The shared raw response enumerates multiple sources.
- The migration is an atomic forward migration; the tested rollback is rollback of
  any failed migration transaction, not a destructive down-migration after new repeated
  data has been collected. Source data is never deleted to restore obsolete uniqueness.
- The preserved overwrite request fields are compatibility fields only; callers now
  receive explicit-repeat conflicts. First-party PVT/screen callers pass attempt IDs.
- Source adapters expose independent acquisition/raw/rating/processing facets and
  preserve existing scoring/qualification distinctions. No scoring, experimental
  geometry, shortcuts, native event streams or manifests were changed.

## Review fix round 1 — I1–I4 and M1

All four Important review findings are addressed together. M1 now has a real
nondefault fit preservation assertion. M2 remains the existing dependency warning;
no warning filter, dependency upgrade or unrelated production change was made.
The review source is `task-2-review.md`, base
`1d9d2e15844d1825506dbb82d070984207e74680`.

### Changes and concrete contract corrections

- **I1:** `InterruptIn` now distinguishes withdrawal, operator_stop,
  hardware_failure, software_failure, planned_interruption and unknown. The older
  participant_stop, technical_failure, lost_connection and other values remain
  accepted/preserved without reinterpretation. No migration rewrites existing causes,
  including NULL/unknown or a nonspecific technical/disconnection record. The picker
  requires an explicit cause choice, including “Cause unknown or not established,”
  before enabling Record interruption; it no longer assigns operator_stop. EN/ES
  choices cover every required cause, reset on context/occasion change, and the typed
  frontend API uses the same interruption union.
- **I2:** added `useAssessmentAdmission` as the shared page admission boundary. It
  prevents duplicate pending requests, freezes a snapshot of the chosen attempt and
  acquisition context, and only admits the response if the page remains mounted and
  its context key is unchanged. It also verifies the returned attempt ID. PVT and
  screen disable participant/visit/picker/start controls while admission is pending.
  Both pages require the admitted snapshot for saving/retrying; neither uses optional
  selectedAttempt IDs nor falls back to legacy ingestion after selection changes.
  PVT snapshots participant, assigned visit ordinal/ID, purpose, locale and fast mode;
  screen snapshots participant, visit ID and purpose. Runner duration/fast-mode settings
  use the admitted purpose/configuration. No stimulus runner implementation changed.
  A stale server start response does not launch KSS or the screen battery. Its durable
  attempt remains available for explicit researcher review; the client does not invent
  an interruption cause or erase that identity.
- **I3:** journey resolves PVT only for PVT or the actual sUAS PVT prerequisite.
  Baseline H10 is resolved only for physiology or its optional mission accompaniment.
  Repeated unrelated PVT/H10 cannot block an exact screen/PVT selection. Optional
  mission H10 repeats require explicit `polar_attempt_id` to report one as complete;
  absent that selection the optional step stays incomplete and does not block the
  mission. Explicit attempt selections validate occasion instrument, participant and
  visit before source lookup. Screen rows are restricted to the requested occasion
  visit. Cross-visit explicit screens return404 rather than reporting their evidence
  under another visit. Historical unknown-visit screens are accessible through the
  deliberate `legacy_screen=true` compatibility path, labeled
  `selection_mode=legacy_screen_visit_unknown` and `assessment_visit_id=null`.
  The default assigned-visit path excludes those unknown-visit rows. No historical
  visit is fabricated and no assignment/classification is silently rewritten.
- **I4:** native source receipt projection now honors `role=ratings`. A questionnaire
  with no rating payload retains its own acquisition/raw/rating/processing facts;
  completed task artifacts do not supply them. Actual ratings_json establishes
  saved raw/ratings; recorded ratings_saved_at additionally establishes finished
  questionnaire acquisition. If the payload exists but its save time is unknown,
  acquisition stays unknown. Task artifact/processing failures do not erase saved
  ratings, and task receipt facts remain on the separately targeted task attempt.
- **M1:** the ambiguous-fit regression seeds nondefault g0/p0/tau0/HCF/version/source
  values and deliberately spaced original JSON, then compares the entire refreshed
  model dump and archive count with their originals. It proves both unchanged fit
  fields and no spurious archive creation, beyond the previous return-value check.

Changed production paths:

```
webui/backend/app/assessment_schemas.py
webui/backend/app/assessment_adapters.py
webui/backend/app/routers/journey.py
webui/frontend/src/lib/assessment-admission.ts (new)
webui/frontend/src/lib/assessments.ts
webui/frontend/src/components/assessments/AssessmentPicker.tsx
webui/frontend/src/app/pvt/page.tsx
webui/frontend/src/app/screen/page.tsx
```

Changed/new tests: `webui/backend/tests/test_assessment_review_fixes.py` (new),
`test_assessments.py`, `test_openmatb_records.py`,
`webui/frontend/src/components/assessments/AssessmentPages.test.tsx` (new), and
`AssessmentPicker.test.tsx`. The only other changed path is this report.

### Exact RED/GREEN evidence

Backend prefix, cwd webui/backend (async worker support enabled):

```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/matb-predictability-testdeps PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 MATB_COMPONENTS=auto /root/repos/MATB/.venv/bin/python -B -m pytest -q -p no:cacheprovider -p anyio.pytest_plugin
```

RED suffix:

```
tests/test_assessment_review_fixes.py tests/test_openmatb_records.py tests/test_assessments.py -k 'category_is_preserved or journey or questionnaire_receipt or refresh_ambiguous'
```

**16 failed, 2 passed, 32 deselected, 1 warning in 2.52s**.
`/tmp/task2-fix1-back-red.log`. New causes were rejected, unrelated instruments blocked
journey/cross-visit screens were accepted, and rating receipts borrowed task facts.
The seeded fit retention test already passed, as expected for M1's coverage issue.

GREEN suffix:

```
tests/test_assessment_review_fixes.py tests/test_openmatb_records.py tests/test_assessments.py tests/test_experiment_safety.py tests/test_hcf_refresh.py
```

**68 passed, 1 warning in 9.45s** (`/tmp/task2-fix1-back-green.log`). This covers every
new category and preserved older category, conflicting cause retries, scoped journey
selection, explicitly labeled unknown-visit compatibility, rating absence/save/task
artifact failure, source/lifecycle/migration preservation and the seeded fit assertion.

Final additional historical-unknown rating regression, same prefix +:

```
tests/test_openmatb_records.py -k 'questionnaire_receipt'
```

**4 passed, 19 deselected, 1 warning in 0.94s**
(`/tmp/task2-fix1-rating-final.log`). Added after the 68-test run; it verifies unknown
questionnaire acquisition before payload and after payload without a recorded save
time. No backend production source changed after the 68-test run. Counts overlap.
All warnings are the pre-existing Starlette python_multipart PendingDeprecationWarning.

Frontend cwd webui/frontend, RED:

```
npm test -- src/components/assessments/AssessmentPages.test.tsx src/components/assessments/AssessmentPicker.test.tsx
```

**10 failed, 2 passed / 2 failed files, 3.60s**
(`/tmp/task2-fix1-front-red.log`). The new page tests exercise both PVT and screen:
controlled deferred start responses, conflicting selection controls, stale participant
updates before response resolution, and clearing/changing current selection/purpose
before save and retry. The real pages and admission/save handlers run; only the
stimulus runners and transport are controlled. Six picker cases cover the required
operator-selected causes and unknown rather than an assigned default.

GREEN:

```
npm test -- src/components/assessments/AssessmentPages.test.tsx src/components/assessments/AssessmentPicker.test.tsx src/lib/assessments.test.ts src/lib/api.test.ts src/lib/pvt.test.ts src/lib/screen.test.ts
npm run typecheck
```

**42 passed / 6 files, 7.81s** (`/tmp/task2-fix1-front-green.log`).
**Typecheck passed** (`/tmp/task2-fix1-types.log`). An initial typecheck found the new
picker test double's callback lacked the real nullable selection signature; corrected
that fixture type and reran typecheck. No frontend production code changed afterward.
`git diff --check` passed.

### Self-review and scope limits

No unresolved I1–I4/M1 concern. Raw snapshots, source IDs, original classification
histories, instrument scoring/geometry and native task artifacts remain unchanged.
Existing historical interruption causes are retained; technical signals do not become
asserted hardware/software causes. The shared start boundary admits an immutable page
context; later live-visit gating/optional runtime lifecycle synchronization remains
Task6. Later assignment and analysis eligibility integration remains with the
controller, as requested. No new browser E2E, hardware run or production migration was
performed for this focused correction. No subagents, push, or sibling worktree edits.

Fix round 1 implementation/report commit:
`458149d79e6206f12e4728cbc0feceb34b88c566`
(`fix: preserve assessment admission context and independent receipts`).
This exact-SHA note is committed separately; it changes no implementation or tests.

## Review fix round 2 — N1 H10 compatibility selection

N1 in `task-2-rereview-1.md` is addressed. Base:
`71f1143fc9889932b5d128c31d56a45a951dde6c`. The prior I1–I4/M1 fixes remain intact.

Only production change: `webui/backend/app/routers/journey.py`. Tests added to
`webui/backend/tests/test_assessment_review_fixes.py`; this report is the remaining
changed file. No frontend, source model, acquisition runtime, migration, raw artifact
or optional-router production code changed.

### Explicit compatibility contract

- Exact existing H10 selections use
  `/journey/{participant}/{visit_ordinal}?experiment=physiology&attempt_id={id}&legacy_polar=true`.
  An optional mission accompaniment uses `experiment=suas&polar_attempt_id={id}&legacy_polar=true`.
- Strict assigned selection remains the default. The compatibility flag admits a
  NULL-visit physiology occasion only when its original origin is legacy or
  legacy_compat, its participant matches, and exactly one linked H10 acquisition
  source records that same participant, matb_session_kind=generic, and the exact
  stored baseline session ID `baseline:{participant}:V{visit_ordinal}`. The check
  follows the immutable source link, not a first/latest capture choice.
- A non-NULL assigned occasion must still match the actual requested Visit ID.
  The compatibility flag cannot override a mismatched assigned visit. Wrong source
  participant or baseline-session context is rejected404. Multiple unselected
  baseline captures still require explicit selection.
- Physiology compatibility responses label
  `selection_mode=legacy_polar_recorded_baseline`, preserve the selected attempt_id,
  and set assessment_visit_id=null. Mission responses separately expose the exact
  polar_attempt_id, polar_selection_mode=legacy_polar_recorded_baseline and
  polar_assessment_visit_id=null; the mission's own context is not relabeled.
- The original occasion visit/phase/origin, capture metadata and purpose ledger remain
  unchanged. The recorded baseline label supports compatibility navigation only;
  it does not establish a frozen study assignment, approval or analysis eligibility.
  No purpose declaration or retrospective classification is added by the reader.

### Regression and verification evidence

The new regression runs twice: once with real normal-declaration source associations
and once with real purpose/shared-assessment migration associations. Each fixture has
two finalized H10 baseline sources whose additive occasions retain visit_id=None;
300-second versus180-second durations produce different completion results to prove
independent exact selection. It also creates wrong-baseline and wrong-participant
sources. The test verifies physiology and optional mission selection for both captures,
compatibility labels, strict-default refusal, wrong-context refusal, and complete
before/after equality of original occasion/capture metadata and purpose history.
A separate assigned-context test uses otherwise qualifying finalized baseline evidence
and proves the flag cannot bypass its different, real assigned Visit ID.

Backend command prefix (cwd webui/backend; async worker support enabled):

```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/matb-predictability-testdeps PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 MATB_COMPONENTS=auto /root/repos/MATB/.venv/bin/python -B -m pytest -q -p no:cacheprovider -p anyio.pytest_plugin
```

RED, same prefix +:

```
tests/test_assessment_review_fixes.py -k 'legacy_polar_exact or polar_compatibility_flag'
```

**2 failed, 1 passed, 14 deselected, 1 warning in0.72s**
(`/tmp/task2-fix2-red.log`). Both declaration and migration cases returned404 for
otherwise valid exact H10 selections; the existing strict assigned-visit case passed.

GREEN auto, same prefix +:

```
tests/test_assessment_review_fixes.py tests/test_assessments.py tests/test_experiment_safety.py tests/test_physiology_api.py
```

**48 passed, 1 warning in5.05s** (`/tmp/task2-fix2-auto-green.log`). This includes the
unchanged optional physiology HTTP workflow and the new cross-component regressions.

GREEN core, same prefix with MATB_COMPONENTS=core +:

```
tests/test_assessment_review_fixes.py tests/test_assessments.py tests/test_experiment_safety.py
```

**46 passed, 1 warning in3.62s** (`/tmp/task2-fix2-core-scoped-final.log`).
The new H10 declaration/migration source-link and journey regressions run in both
component profiles. No optional HTTP router was added to production core routing.

Final stricter fixture check (after making the mismatched assigned source otherwise
qualifying/finalized), auto prefix +
`tests/test_assessment_review_fixes.py -k polar_compatibility_flag`:
**1 passed, 16 deselected, 1 warning in0.25s** (`/tmp/task2-fix2-strict-final.log`).
No production source changed after the48/46-test runs. Counts overlap.

Scope correction: an initial core command incorrectly included the existing optional-
only `tests/test_physiology_api.py` and produced **2 failed, 46 passed, 1 warning
in5.91s** (`/tmp/task2-fix2-core-green.log`): those two tests expected optional routes
on the global core app. The controller confirmed core CI deliberately excludes that
file. A brief uncommitted fixture-isolation experiment was removed completely at the
controller's direction; its exploratory runs are not final-source verification.
The file has no diff. Final core evidence uses the appropriate shared subset above,
and the original optional HTTP workflow remains covered by the48-test auto run.

`git diff --check` passed. All warnings are the existing python_multipart pending
deprecation; no suppression or dependency change. No frontend tests/build were rerun,
because this correction changes no frontend. No hardware/production migration/push,
subagents or sibling worktree changes. No unresolved N1 blocker; remaining study
assignment/eligibility integration stays with the controller as previously scoped.

Fix round2 implementation/test commit:
`577cf8624aa3f2b88aa2084b307fc18c13ddfb9a`
(`fix: select legacy H10 attempts through recorded baseline context`).
The report is committed separately to record this exact source commit.
