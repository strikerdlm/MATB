# MATB repeatable-study implementation plan

> Execute task-by-task with focused regression evidence and independent review.

**Goal:** Complete the P0+P1 repeatable-study release and whole-study restoration.
**Architecture:** Extend the current single-owner FastAPI/SQLite console with shared
occasion/attempt identities, immutable protocol/analysis records, and administrative
lifecycle adapters. Keep native/mission/browser/physiology task implementations.
**Tech stack:** Python 3.12+, SQLModel/Pydantic/FastAPI; Next.js/React/TypeScript;
existing pytest, Vitest and Playwright gates, SQLite and local immutable artifacts.
**Spec:** `docs/superpowers/specs/2026-09-10-repeatable-study.md`.

## Global constraints

- P0+P1 are in this release; P2 synchronization/replay, automated station inventory,
  generated capability reporting and shared-network authentication are deferred.
- Preserve raw observations, existing source IDs/hashes, instrument scoring,
  experimental geometry, task shortcuts and qualification distinctions.
- Keep SQLite, independent local study workspaces and existing backend protections.
- Rules are researcher-authored before real activation; approvals are named local
  attestations. Synthetic examples are not scientific approvals or hardware evidence.
- Historical unknowns require recorded classification AND analysis-plan permission.
- Protect whole live visits from heavy work, allowing prescribed co-acquisition.
- Descriptive reproduction only; existing inferential engines stay explicitly separate.
- English/Spanish operational UI; no added stimulus-time prompts or decorative motion.
- Preserve the original checkout. Work only in the repeatable-study worktree.

## Task 1: Explicit purpose provenance and accurate overview

**Files:** acquisition schemas/routers/runtimes and their SQLModel records under
`webui/backend/app`; new focused purpose provenance models/service/router; `db.py`
migrations; API callers/types/fixtures; README and affected acquisition examples.

**Produces:** append-only, stable purpose provenance identity plus reusable service
for new declarations, historical migration, retrospective classification and views.
Document exact interfaces in the task report for Task 2/5 consumers.

- Require purpose in NEW HTTP acquisition request contracts for PVT, screen,
  OpenMATB, Liftoff, mission and H10. Do not remove tolerant defaults from historic
  artifact readers. Update first-party callers and intended valid test payloads.
- Reject study + fast/technical practice conflicts; never silently downclassify an
  explicit contradictory new request. Parent study suites may still contain explicitly
  protocol-declared practice blocks; their actual capture purpose remains practice.
- Add append-only classification history (`explicit`, `retrospective`, `unknown`)
  with actor/time/reason/supporting references as applicable. Give declarations stable
  identities so legacy integer-ID reuse/overwrites cannot bind another raw observation's
  classification. New declaration is atomic with acquisition record persistence.
- Migrate historic data idempotently, preserving the recorded purpose while labeling
  unsupported prospective intent unknown. Existing fast-mode inference must become a
  documented system classification, never a fictitious human decision/date. Stop the
  old migration from repeatedly rewriting newer classifications at every startup.
- Expose provenance/history/classification through the protected backend and additive
  record views. Named reviewer/reason required for retrospective classifications;
  ordinary clients cannot label historical records prospectively explicit.
- Correct README obsolete pre-v3/future-reconciliation claims and overview tables.
  Keep CSV-only metrics provisional, and physics/human validation limitations explicit.
- TDD: omitted-purpose rejection per acquisition API; contradictory requests;
  migration rerun, unknown vs explicit, stable provenance through archived replacement,
  immutable reclassification history and first-party valid request compatibility.
- Run focused backend acquisition/migration tests, frontend affected tests/typecheck,
  documentation verification. Report commands/results and source changes; commit.

## Task 2: Shared occasions, attempts and repeated assessments

**Files:** focused `assessment_models.py`, `assessment_schemas.py`,
`assessment_service.py`, `routers/assessments.py`; existing models/db migration,
PVT/screen handlers; native/mission/Liftoff/physiology adapters; journey/catalog/metrics
readers and frontend API types. Split helpers by responsibility if needed.

**Consumes:** Task 1 provenance identity/service.
**Produces:** occasion/attempt APIs, stable links to instrument records, common
receipt facets, explicit repeat and idempotent finalization, migration report.

- Create occasions with participant, nullable legacy-only visit, instrument, phase,
  order, condition, version reference and origin. New study occasions require real
  assigned visits; do not invent visits/phases for unknown historic screens.
- Attempts have opaque stable IDs, occasion, ordinal, purpose reference, repeat-of/
  reason, interruption category, acquisition state/times and instrument source link.
  Questionnaire attempts bind the exact target task attempt; physiology can be an
  explicitly accompanying occasion in a common collection group.
- Transactionally rebuild PVT/screen uniqueness to attempt identity, preserving IDs,
  raw payloads and archived retakes; retain legacy CSV Block table unchanged. Migrate
  existing instrument instances to shared links without rewriting native manifests.
- Add explicit attempt creation/repeat/start/finish/interruption/read/list surfaces.
  Retry the same final payload idempotently; reject differing content. Stop destructive
  acquisition overwrite semantics and give clients an actionable repeat response.
- Attach IDs to native block/rating instances, Liftoff/mission session instances,
  and H10 recordings. Keep independent receipt facets for raw saving, acquisition,
  ratings and processing; unknown legacy facets remain unknown.
- Update PVT/screen APIs and first-party clients for independent occasion/attempt
  reopening, including raw evidence retrieval. Existing legacy history remains
  readable; active new-study collection will be assignment-gated by Task 3/4.
- Replace latest/first-row assumptions in journey/completeness/discovery/export
  consumers with explicit occasion/attempt selections. Legacy compatibility readers
  are labeled and must not silently collapse new repeats into visit/workload cells.
- TDD: three PVT occasions one visit, independent raw retrieval, repeated screens,
  interrupted repeat retained, duplicate finalization vs conflict, exact questionnaire
  target, raw/ID-preserving rerunnable migration and rollback on injected failure.
- Run covering tests, report all concrete APIs/links for later tasks, and commit.

## Task 3: Frozen StudySpec and AnalysisPlan registry

**Files:** focused study-spec/analysis-plan schemas/models/services/routers;
study binding/enrollment helpers; schema-driven researcher editors and API types.

**Consumes:** Task 2 occasion creation and assignment/attempt views.
**Produces:** immutable versioned specs/plans, validation/rehearsal/approval records,
explicit assignment activation and amendment APIs, authored-rule editors.

- Add StudySpecV1 and AnalysisPlanV1 canonical payload fingerprints and immutable
  version identities; references use stable version IDs (avoid mutually nested hash
  cycles). Freeze enabled instruments, phase/order/condition/assignment, preparation,
  repeat/interruption rules, exact instruction/language/scenario/visual/input/scoring
  bindings; outcomes/contrasts/unit/exclusions/denominators/qualification/pooling.
- Ship constrained longitudinal, pre/post/recovery and repeated-block templates.
  Preserve ASTRA/six-visit compatibility without inventing new approved scientific
  criteria for existing deployments. Templates/examples remain visibly synthetic/draft.
- Implement draft editing, structural/semantic validation, isolated synthetic rehearsal
  against actual occasion/attempt services, named attestation approval/freeze, then
  explicit collection activation. Required researcher-authored rules cannot default
  to arbitrary competence or analysis thresholds. Unsupported bindings reject validation.
- Materialize assigned occasions from the exact active version, recording actual
  condition assignment. Started visits never change. Amendments identify unstarted
  assignments explicitly and record applicability/actor/reason/diff.
- Preserve deployment/workspace mismatch protection; bind the workspace to a study
  identity/template family plus immutable version history, not a mutable singleton.
- New study acquisition must resolve assignment participant/visit/purpose/config on
  the server and reject mismatch/direct unassigned study starts. Standalone practice
  and historical read-only views remain usable. Update applicable frontend callers.
- Build usable English/Spanish constrained authoring/validation/rehearsal/freeze and
  amendment UI, with exact version links and required criteria explanations.
- TDD: immutability, semantic bad references, rules missing, synthetic isolation,
  rehearsal identity invalidated by editing, approval bound to hash, wrong workspace,
  assignment mismatch, explicit future amendment and started-visit preservation.
- Report schemas/APIs for Task 4/5/6 and commit after covering gates.

## Task 4: Measurable preparation, exposure and assigned study UI

**Files:** preparation/exposure models/service/router and instrument adapters;
study/participant/visit/assigned-session frontend; participant flow components;
existing session/catalog navigation as integration requires.

**Consumes:** immutable specs and assigned attempts from Task 2/3.
**Produces:** version/config-bound preparation evidence, exposure history, researcher
study-first navigation and common participant next-action/receipt contract.

- Distinguish demonstration, acknowledgment, comprehension, practice and competence;
  save item responses/failures/repeats, actual practice observations and criterion
  identity. No self-attested checkbox may count as objective practice evidence.
- Generate task/control labels and required items from enabled tasks and resolved
  session mappings. Unknown/unresolved mapping blocks preparation with recovery.
  Use existing task practice implementations/recorded actions; keep experimental
  engines/stimulus logic unchanged. Approved criteria operate on actual observations.
- Exposure records are participant/instrument/version/config/attempt-linked and
  include trustworthy duration/repeats/outcome; unknown historic times remain unknown.
- Gate baseline/condition acquisition on required preparation. Later training is
  permitted only if explicitly prescribed by the frozen protocol. Mapping/version
  changes invalidate mismatched prior competence, never silently reuse it.
- Researcher route: study → participant/visit → planned assessments → live session
  → evidence → analysis. Primary launch uses assignment-bound config. Catalog stays
  available for practice/exploration. Include migration classification UI/history.
- Participant route shows one next action with consistent prepare/understand/practice/
  ready/perform/ratings/finish terminology and existing help/stop access; preserve
  instrument-specific implementations and no new task-time popups or key bindings.
- Add common receipt facets and pending/failed/unknown recovery states. Exact-target
  questionnaire drafts and independently reopened attempts must work across this flow.
- TDD/unit/browser: separate preparation stages, disabled-task omission, mismatched
  control mapping, failed competence/repeat exposure, assigned config spoof rejection,
  actual PVT/native/rating navigation, English/Spanish and keyboard help/stop.
- Report endpoints/adapter behavior and commit after covering gates.

## Task 5: Immutable HCF, plan eligibility and descriptive reproduction

**Files:** HCF derivation model/service and legacy HCF refresh integrations;
plan eligibility/compatibility/frozen input/descriptive execution modules and router;
analysis/evidence researcher UI and offline descriptive verifier.

**Consumes:** provenance, attempts/occasions, frozen plans/specs, preparation evidence.
**Produces:** append-only HCF derivations and explicit frozen descriptive analyses,
eligibility/condition comparison reports, data+plan fingerprints and offline replay.

- Replace mutable hcf_value/source refresh with immutable derivations containing
  reference screen IDs, cohort fingerprint, mapping version/time and values. Exactly
  one plan-designated screen attempt per participant; no repeat cohort weighting.
  Preserve legacy values/snapshots with unknown unrecoverable reference cohort.
  Current exploratory pointer may change; frozen fit/result/figure must not.
- Evaluate plan-specific source/purpose/occasion/preparation/repeat/interruption,
  timing/human qualification and pooling requirements separately. Unknown facts fail
  that criterion without inventing evidence. History classification only permits
  inclusion when the plan allows retrospective inclusion. Explain criteria with links.
- Compare available task/instruction/language/visual/input/timing/scoring configuration
  identities before pooling. Require plan-permitted named rationale for differences;
  unknown does not mean equal; no claim of psychometric/perceptual equivalence.
- Freeze selected attempts/metrics/eligibility/qualification snapshots/HCF/comparison
  under data and plan fingerprints. Later revocation/classification/cohort change
  leaves frozen artifacts unchanged but current applicability is displayed separately.
- Explicitly execute existing instrument calculations and prespecified occasion
  differences/aggregations; record exact implementation/dependencies/config/inputs.
  No automatic Bayesian/Suhir fitting or native-metric promotion. Legacy inferential
  endpoints stay explicitly separate. Reproduce descriptive artifacts offline.
- UI: select a frozen plan, inspect included/excluded occasions and denominators,
  navigate criteria, compare HCF/analysis derivations, run/freeze/export/reopen by ID.
- TDD: cohort growth immutable old value/figure, deterministic screen selection,
  incomplete denominator and repeat rule, qualification/purpose unknown exclusion,
  invalid pooling rationale, stable fingerprints, revocation history, offline replay.
- Report execution/artifact interfaces for restoration and commit after covering gates.

## Task 6: Whole-visit acquisition reservation and bounded jobs

**Files:** acquisition/job models/service/router; backend lifespan/owner lease;
native/PVT/screen/mission/Liftoff/H10 start adapters and browser acquisition hooks;
heavy import/evidence/analysis/export/geography entrypoints; administrative job UI.

**Consumes:** study live-session/attempt identity; existing backend instance ownership.
**Produces:** durable atomic admission, acquisition reservation, bounded heavy queue,
maintenance state and recovery API used by Task 7.

- Reserve from opening live collection until explicit researcher close, including
  ratings/recovery gaps. Protect standalone timed practice for its acquisition window.
  Permit only protocol-declared concurrent acquisition, e.g. H10 alongside foreground
  MATB, with participant/visit association checked. One foreground timed task at a time.
- Heavy work (imports/reconcile/analysis/large exports/assets/backups) queues until no
  reservation, one heavy job runs at a time. A running job blocks opening acquisition;
  explicit cancellation must establish safe termination before releasing ownership.
  Keep bounded necessary raw recording/markers/status/preparation feedback functional.
- Admission checks are atomic across simultaneous requests and reuse the existing
  single-backend owner lease. Integrate all start surfaces including native previews,
  browser timed tasks and physiology; no optional bypass through direct HTTP routes.
- Preserve durable queue, job state/errors, bounded payloads and deduplication;
  worker exceptions release capacity safely. Refuse unbounded uploads while reserved.
- Disconnect/restart is not proof of station idle: retain uncertain reservation and
  interrupt attempts, reconcile actual native processes, require explicit idle recovery
  when browser ownership cannot be established. Never silently resume lost acquisition.
- Display pending work/block reason/next action and explicit close/recovery/maintenance.
  Keep stop and recording shutdown available while queued/blocked.
- TDD: atomic competing starts, MATB+H10 allowed vs disallowed pairs, all heavy routes
  deferred in ratings/recovery, active job blocks launch, disconnect/PID/restart, queue
  limits/cancel/failure/shutdown. Measure synthetic sample/queue/frame/disk observations
  with explicit software-only status and include runnable load-matrix harness.
- Report maintenance/queue/artifact APIs and commit after covering gates.

## Task 7: Whole-study restoration and release verification

**Files:** Research Console backup/restore service/CLI/router + researcher controls;
offline replay package integration; full-study fixtures/E2E/CI and verification docs.

**Consumes:** all prior immutable identities/artifacts and maintenance coordinator.
**Produces:** consistent checksummed study bundles, safe empty-workspace restore,
offline reproduction report, reviewed release and passing Linux/Windows CI.

- Backup only under exclusive maintenance with no live collection/writers. Snapshot
  SQLite consistently and inventory raw native/physiology/evidence artifacts, frozen
  configs, classifications/exposure, specs/plans/HCF/analyses/figures. Verify hashes.
- Preserve original manifests/bytes and use artifact logical-path resolution for
  relocated workspaces. Detect missing/corrupt required sources; incomplete artifacts
  remain explicitly incomplete, never silently ignored/promoted.
- Restore only to an empty destination, validate safe archive members/checksums and
  FK/semantic identities before activating staged output. Roll back failure, never
  overwrite an existing study. Exclude reusable secrets/live leases and do not resume
  interrupted acquisition. Verify workspace binding and regenerate operational tokens.
- Include analysis source/version and locked dependency requirements; matching offline
  dependency kits support Linux and Windows. Restore rehearsal starts empty, verifies
  original source hashes/plan/data fingerprints and recomputes selected descriptive
  outcomes and comparisons without internet. Preserve frozen exported figure bytes.
- Full synthetic acceptance: preparation → baseline PVT → native MATB+H10 → post-task
  PVT → recovery → recovery PVT → evidence → frozen descriptive results → backup →
  restore and reproduce. Include a repeat/interruption/classification/amendment case.
- Finish English/Spanish keyboard/browser matrix at 1280×720, 1366×768, 1920×1080,
  smaller researcher layout and browser zoom, with no unexpected page errors.
- Run full backend/core/component/native/contracts/frontend/lint/typecheck/build/docs
  and required browser tests. Add repeatable-study gates to GitHub Linux/Windows.
  Fix actual failures, no weakened assertions/retry-only acceptance.
- Write verification record with exact software evidence and physical/human limits;
  independently review the whole branch. Commit, push/open reviewable PR(s) and ensure
  final GitHub checks pass. Do not merge or deploy an active study.
