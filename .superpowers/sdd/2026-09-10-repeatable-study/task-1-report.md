# Task 1 implementation report

Status: implemented and verified; ready for independent review. Work performed only
in `/root/repos/MATB/.worktrees/repeatable-study`, base `7264b4b`. No push, merge,
production dataset access, or subagent delegation.

## Changes

- NEW HTTP requests explicitly require execution purpose for PVT, screen,
  OpenMATB, Liftoff, H10, participant mission, and technical mission. Participant
  mission requests require `study`; technical mission requests require `practice`.
- Contradictory study + fast screen/PVT requests return 422. Screen fast-mode
  values must be booleans, closing a discovered loose-dictionary bypass whereby
  a truthy nonboolean could skip the full study protocol validation.
- New acquisition records receive a UUID `purpose_provenance_id`, an immutable
  source identity with original metadata snapshot SHA-256, and an explicit
  declaration within the same database transaction. No declaration API permits
  clients to assign historical records a prospective explicit classification.
- Added append-only `purpose_provenance` and `purpose_classification` SQLModel
  tables with SQLite UPDATE/DELETE rejection triggers. History records purpose,
  classification, actor, actual recording time, reason, and supporting references.
- Added protected local GET history and POST retrospective-classification routes.
  Reviewer/reason are required and whitespace-only values fail. System actor
  prefixes are reserved. Existing Host/Origin/bearer protections apply.
- Archive replacements retain the original UUID both on `ArchivedAssessment`
  and in its unchanged original-record snapshot. Numeric SQLite ID reuse cannot
  attach the replacement observation to the prior classification history.
- Migration preserves recorded purpose/raw values/scores/dates, labels unsupported
  historical prospective intent `unknown`, and records the prior fast-screen or
  invalid-v1-PVT inference as a system retrospective classification at migration
  time. Historical practice rows remain unknown, regardless of their existing
  `created_at` date. Legacy archived assessments are migrated too. Reruns skip
  records already linked to identities and do not append duplicate history or
  overwrite later reviews.
- Removed the old experiment-execution migration's recurring UPDATE statements
  that rewrote historical purpose on every startup. Its column additions and
  migration marker remain idempotent. Existing migration tests now assert source
  purpose preservation, with the new suite separately verifying system inference.
- Record views expose the UUID for PVT, screen, suite sessions, Liftoff, H10 and
  mission (including recovered mission handles). Historical artifact readers keep
  their defaults. Regenerated the additive H10 checked-in JSON schema.
- First-party frontend request types, setup calls, screen API adapter, backend
  valid request fixtures, browser acquisition fixtures and sUAS API example now
  declare purpose. Existing UI purpose choices remain in place; no stimulus-time
  interaction or experimental geometry changed.
- Updated EN/ES README overview and module tables to describe implemented v3
  paired capture ingestion/reconciliation; CSV-only metrics remain provisional
  and confirmatory-ineligible. Physical timing and human calibration limitations
  remain explicit. Updated backend and Console example contract documentation.
  Documentation checks also exposed and repaired pre-existing EN/ES `/start` and
  `/tracker` token drift by moving the Spanish workspace paragraph to the Spanish
  README and correcting its tracker route.

## Exact interfaces for Tasks 2 and 5

Module: `app.purpose_service` (imports core SQLModel metadata only; no optional
runtime imports).

- `declare_acquisition(db: Session, row, *, purpose: str) -> str`: internal NEW
  acquisition persistence hook. Accepts a supported transient source model with
  `purpose_provenance_id is None`; validates purpose and any source purpose field,
  adds/flushed source and ledger rows, sets the UUID on the source. Does NOT commit.
  The caller owns commit/rollback. Do not call it for historical imports, already
  persistent records, archived originals, or retrospectively reconstructed facts.
- `classify_retrospectively(db, identity, *, purpose, reviewer, reason,
  supporting_references=()) -> PurposeClassification`: appends one event. Allowed
  purposes: study/practice/exploration. Nonblank named reviewer and reason required;
  reviewer prefixes `system:` and `local:` reserved. Raises `ValueError` for invalid
  input and `KeyError` for absent identity. Does NOT commit or change source purpose.
- `provenance_view(db, identity) -> dict`: returns `id`, `source_table`, `source_id`,
  `source_snapshot_sha256`, `recorded_purpose`, `created_at`, `current`, and ordered
  `history`. Each event contains `id`, `provenance_id`, `purpose`, `classification`,
  `actor`, `reason`, `recorded_at`, and decoded `supporting_references`.
- `migrate_purpose_provenance(engine) -> None`: idempotently creates ledger tables,
  adds nullable identity columns to installed acquisition tables, and migrates
  still-unlinked rows. Called by `init_db` after existing execution column migration.
- `GET /purpose-provenance/{identity}`: identity + full history; absent returns 404.
- `POST /purpose-provenance/{identity}/classifications`: strict JSON body
  `{purpose, reviewer, reason, supporting_references?: string[]}`; returns 201 with
  updated view. No `classification` argument allowed; any such field returns 422.
- Source model identity columns: `ScreenResult`, `PvtAssessment`, `PracticeResult`,
  `ArchivedAssessment`, `OpenMatbSuiteSession`, `LiftoffSession`,
  `PolarCaptureRecord`, `SimulationSession`, `TechnicalSimulationSession`.
- Actual table names: `screenresult`, `pvt_assessment`, `practiceresult`,
  `archived_assessment`, `openmatb_suite_session`, `liftoff_session`, `polar_capture`,
  `simulation_session`, `technical_simulation_session`.

**Consumer rules:** Link attempts/selection to `purpose_provenance_id`, never just
integer source ID. `recorded_purpose` describes the original record; `current` is
the latest classification. An initial `unknown` event remains in history after
review. `explicit` actor is `local:acquisition-request` and attests a new explicit
request, not scientific approval. Migration creates `unknown` events with actor
`system:migration`; for prior fast-mode inference it appends `retrospective` /
`practice` with the SAME system actor, not a named human review. Task 5 must
therefore distinguish system inference from named local retrospective attestation
and require analysis-plan permission for historical unknown observations. This
Task does not add cohort/analysis eligibility gates. Protocol-declared OpenMATB
practice block captures already retain actual practice purpose inside study suites;
that behavior is preserved and covered by the existing record/runtime tests.

## TDD and verification evidence

Backend command prefix (cwd `webui/backend`; async checks executed escalated to
avoid the known sandbox threadpool limitation):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/matb-predictability-testdeps PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 MATB_COMPONENTS=auto /root/repos/MATB/.venv/bin/python -B -m pytest -q -p no:cacheprovider -p anyio.pytest_plugin
```

RED, before implementation: prefix + `tests/test_purpose_provenance.py` yielded
**10 failed**: six missing/defaulted request purpose contracts, omitted screen
purpose accepted by OpenAPI, fast-study PVT accepted, missing migration/service,
and missing atomic declaration service. Test collection also caught and corrected
one authoring-only SQL `:true` bind-token issue before the migration assertions ran.

Intermediate acquisition run: 66 passed / 6 failed from old Liftoff request fixture
omission and missing additive H10 view field; corrected both. Expanded run then
reported 151 passed / 9 failed, all from newly written cross-test imports omitting
`tests.`; these were corrected without changing behavioral assertions.

GREEN expanded suite, prefix +:

```text
tests/test_purpose_provenance.py tests/test_db_migrations.py
tests/test_pvt_endpoint.py tests/test_screen_endpoint.py
tests/test_openmatb_runtime.py tests/test_openmatb_records.py
tests/test_liftoff_endpoints.py tests/test_physiology_api.py
tests/test_physiology_runtime.py tests/test_simulation_endpoints.py
tests/test_simulation_runtime.py tests/test_simulation_models.py
tests/test_experiment_safety.py tests/test_hcf_refresh.py
```

**160 passed, 5 warnings in 62.77s.** Output `/tmp/task1-green.log`. Warnings were
existing python_multipart and legacy SQLModel query deprecations.

Additional self-review RED: prefix + `tests/test_purpose_provenance.py -k non_boolean`
produced **4 failed**, proving nonboolean fast-mode values were accepted. Output
`/tmp/task1-fast-red.log`. Fixed strict boolean checking, and added historical
practice-date/archive preservation and recovered mission-view linkage checks.

Final affected GREEN: prefix + `tests/test_purpose_provenance.py
tests/test_screen_endpoint.py tests/test_simulation_runtime.py` produced
**49 passed, 1 warning in 26.83s** (`/tmp/task1-final-focused.log`).
Prefix + `tests/test_simulation_failures.py` produced **4 passed, 1 warning in
4.95s** (`/tmp/task1-simulation-failures.log`). These final commands cover source
changes made after the 160-test run; the counts overlap and must not be added as
unique tests.

Frontend (cwd `webui/frontend`):

```sh
npm run typecheck
npm test -- src/lib/api.test.ts src/lib/simulation/api.test.ts src/lib/liftoff/api.test.ts src/lib/physiology/api.test.ts src/lib/pvt.test.ts src/lib/execution-purpose.test.ts src/components/mission/setup src/components/liftoff/LiftoffSetupForm.test.tsx src/app/pvt/page.test.tsx src/app/openmatb/setup/page.test.tsx
```

**Typecheck passed. 46 tests passed / 10 files, 24.71s.** Outputs
`/tmp/task1-types-green.log` and `/tmp/task1-front-green.log`. Earlier red frontend
checks found two stale exact-request expectations and two missing purpose fixture
properties; callers/expectations were updated to the required contract. Read
`webui/frontend/AGENTS.md` and installed Next `use-client.md` before frontend edits.
No browser E2E was run; acquisition fixture changes are included in typechecking.

Repository documentation:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/matb-predictability-testdeps PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /root/repos/MATB/.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_readme_documentation.py tests/documentation/test_documentation.py
```

**47 passed / 3 skipped, 1.11s** (`/tmp/task1-docs-green.log`). Initial run found
bilingual route-token drift described above; no tests were weakened.
Same prefix + `tests/physiology/test_contract_schemas.py`: **1 passed, 1.55s**
(`/tmp/task1-schema.log`). `git diff --check` passed.

Core-only smoke verification (cwd backend): `MATB_COMPONENTS=core`,
`MATB_DB_PATH=/tmp/matb-task1-core.sqlite`, `PYTHONPATH=/tmp/matb-predictability-testdeps`,
venv Python `-B`: imported `app.main`, ran `init_db()`, asserted PVT and purpose
history paths in OpenAPI, and asserted none of Liftoff/OpenMATB/physiology/simulation
runtime modules were imported. **Passed** with fresh local SQLite. Auto-component
coverage is provided by the expanded acquisition suite. No production DB migrated.

## Self-review and limits

- Verified provenance survives a real HTTP overwrite and archive snapshot; both
  practice and study declarations are atomic with SQL persistence/rollback.
- Verified all seven omission routes reject otherwise-valid bodies solely for
  missing `body.execution_purpose`; study/technical conflict tests use otherwise
  valid request bodies to prevent false-positive validation failures.
- Verified unknown history is not upgraded on migration rerun, historical practice
  creation dates remain unchanged, system classification has no invented human
  actor/date, and reviewer events cannot edit earlier rows through SQL or API.
- Verified core-only startup and checked-in H10 schema parity. Optional artifact
  reader defaults remain tolerant. CSV-only scientific limitations remain clear.
- Purpose UUID columns are nullable for historical-reader compatibility. Installed
  startup migration fills existing records; direct historical fixture/import rows
  must run migration rather than `declare_acquisition` to become classifiable.
- The snapshot SHA-256 seals metadata at identity creation. It is not a claim of
  independent physical timing, human validation, consent or scientific approval.
- System-inferred practice classifications are identifiable system events; later
  analysis eligibility must not mistake them for named retrospective reviews.
- No unresolved blocker. Independent review and subsequent task gates remain
  root responsibilities. No changes to instrument scoring or experimental controls.
