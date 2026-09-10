# Repeatable study release — approved specification

The user approved implementation of the P0+P1 plan on 2026-09-10, based on main
`a3b840a2d0a93380104b5a45f520a1502115c2a8`. This document preserves the approved
requirements and the choices made during planning.

## Goal and binding choices

Run one complete, repeatable study across instruments with no ambiguity about
what was planned, what happened, what was saved, and what may be analyzed.

- P0+P1 are in this release. P2 automatic station inventories, synchronization
  uncertainty/replay, generated capability reporting and authenticated shared
  network roles remain a separate release.
- Acceptance sequence: preparation, baseline PVT, native MATB with H10, post-task
  PVT, recovery, recovery PVT, evidence review, frozen descriptive analysis,
  complete backup and offline restoration/reproduction.
- Researchers author justified competence criteria, repeat rules and outcomes
  before activation. Synthetic examples are software fixtures, not scientific
  approvals or universal thresholds.
- Named local reviewer attestations record approval; they are not authenticated
  multi-user authorization.
- Historical unknown purpose/occasion requires documented classification AND
  permission in a new analysis plan before inclusion. Preserve prior frozen
  outputs and visibility of unknown history.
- Reserve the station throughout a live visit, including ratings and recovery;
  heavy work waits until the researcher closes collection. Scheduled concurrent
  physiology is permitted.
- P1 supports explicit descriptive reproduction, existing instrument calculations,
  HCF derivations and prespecified occasion contrasts. Existing inferential engines
  remain a separate explicit workflow.
- Keep SQLite, independent local study workspaces, existing instrument behavior,
  raw evidence, IDs/hashes, score definitions and qualification distinctions.

## Required deliverables

1. Require purpose at every acquisition entry point (PVT, screen, native MATB,
   Liftoff, mission, H10), reject study/fast-practice contradictions, update callers
   and examples. Append-only explicit/retrospective/unknown provenance records;
   idempotent historical migrations must not invent intent, actors or dates.
   Reconcile README v3 implementation status against the authoritative pipeline;
   keep legacy CSV provisional and scientific limitations accurate.
2. Scheduled occasions identify participant, visit, instrument, phase, planned
   order, condition and frozen protocol version. Attempts represent every actual
   execution, repeat, practice and interruption. Move PVT/screen uniqueness to
   attempts, preserve existing IDs/raw payloads/archived retakes in transactional
   migrations, retain unassigned historical screens. Link native block instances,
   questionnaire submissions, Liftoff/mission and physiology without rewriting
   immutable source IDs. Idempotent finalization; conflicting submissions rejected;
   acquisition overwrites become explicit repeats with reasons. Completeness,
   journey, discovery and exports must not use latest-result selection.
3. Constrained, versioned StudySpec and AnalysisPlan editors with longitudinal,
   within-visit pre/post and repeated-block/recovery templates; preserve ASTRA and
   six-visit compatibility schedules. Freeze enabled instruments, occasions,
   condition assignment, preparation, repeats, interruptions and exact instruction,
   language, scenario, visual, input and scoring versions. Plans declare outcomes,
   experimental units, contrasts, exclusions, attempt selection, incomplete-data
   denominators, qualification and pooling rules. Draft → validate → isolated
   synthetic rehearsal → named approval/freeze → collect. Real activation requires
   authored rules. Amendments explicitly affect identified unstarted assignments;
   started visits keep their version. Preserve workspace mismatch rejection.
4. Distinguish demonstration, acknowledgment, comprehension, practice and competence;
   instructions/checks derive from enabled tasks and resolved device mapping.
   Retain responses, failures, repeats, actual practice evidence and criterion
   versions. Maintain participant exposure by instrument/configuration/version,
   marking unknown historical details. Prepare before baseline/condition by default;
   later training requires explicit protocol prescription. Researcher flow is study
   → participant/visit → assignments → live session → evidence → analysis. Server
   resolves and validates assignment configuration. Participant has one next action,
   consistent preparation/ready/acquisition/ratings/finish semantics and help/stop;
   no new prompts, animations or shortcut changes during timed tasks.
5. Immutable HCF derivations record selected screen IDs, cohort fingerprint, mapping
   version and timestamp; one designated screen attempt per participant prevents
   repeat weighting. Preserve legacy values with unknown unrecoverable provenance.
   Exploratory recalculation never mutates frozen results. Plan eligibility explains
   precise criteria/evidence separately from source completeness, hardware/human
   qualification. Compare task, instruction, language, visual, input, timing and
   scoring contexts before pooling, requiring plan-permitted rationale for differences
   and treating unknown context as unknown. Freeze attempts, metrics, eligibility,
   HCF and comparison into data+plan-fingerprinted inputs. Explicit descriptive runs,
   immutable figures, offline reproduction; no automatic inferential promotion.
6. Shared, durable reservation/job coordinator extends existing backend ownership.
   Gate all instrument start boundaries including browser tasks and native previews;
   allow only prescribed co-acquisition. Queue imports/reconciliation/analysis/large
   export/asset preparation/backup through protected visits; necessary bounded
   recording/marker/status writes remain available. One heavy job at a time; a running
   heavy job blocks opening a visit until completion or safe explicit cancellation.
   Admission is atomic. Preserve uncertain/interrupted ownership across disconnects
   and restarts; heartbeat loss alone does not establish that acquisition stopped.
7. Maintenance-mode consistent backup includes SQLite, raw native/physiology/evidence,
   configs, classifications, exposure, plans, derivations and exports. Checksummed
   inventory, original manifest bytes preserved, relocated artifact resolution.
   Restore only to empty workspace with integrity/FK verification; never reuse live
   credentials/leases or resume interrupted collection silently. Include analysis
   source/version/dependency requirements and verify with matching offline dependency
   kit on supported operating systems. Restoration report compares source hashes,
   frozen identities and recomputed outcomes. ZIP creation alone is not acceptance.

## Cross-cutting acceptance

- Shared versioned StudySpecV1, AnalysisPlanV1 and receipt contracts; instrument
  payload/scoring formats stay instrument-specific. Study starts require assignments;
  standalone practice remains accessible from the catalog.
- Receipt facets: preparation, acquisition outcome, raw saving, ratings, processing,
  plan eligibility. Interruptions distinguish withdrawal/operator stop/hardware
  failure/software failure/planned interruption.
- Test purpose omissions, transactional/idempotent migration, three independently
  reopened PVTs, repeats/conflicting saves, exact-target questionnaire recovery,
  frozen amendment boundaries, mapping-sensitive preparation, immutable HCF/reporting,
  planned repeat selection and denominators, criterion explanations, contention,
  disconnect/restart/shutdown/queue limits and full restored analysis.
- Record software dropped samples/overflow/frame gaps/disk-pressure/timing observations;
  do not represent synthetic checks as hardware qualification or human validation.
- Finish full Linux/Windows CI; English/Spanish browser flows, keyboard, normal desktop
  sizes, smaller layouts and zoom. Upgrade only between live sessions with a backup.
