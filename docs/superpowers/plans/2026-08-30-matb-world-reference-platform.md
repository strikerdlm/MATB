# MATB World-Reference Platform Execution Plan

**Date:** 2026-08-30
**Baseline:** `48e9dbaa946349021d2ce2186d599c1f82182ab4` (`origin/main`)
**Strategy:** open research core, offline-first lab workstation, product-family architecture, independent evidence gates

## Mission

Build the strongest scientifically defensible MATB platform in the lineage by combining measurement-grade provenance, deterministic experiments, modern adaptive automation, excellent lab usability, and public qualification evidence. Software capability and empirical validation remain separate claims.

## Non-negotiable scientific rules

1. The immutable event stream is the scientific source of truth.
2. Scheduled time, software dispatch, physical onset, physical input, receipt time, and synchronization-clock time are distinct observations.
3. A missing physical or human observation stays missing; software evidence never upgrades another evidence class.
4. Scenario specifications, seeds, compiler versions, manifests, component versions, and hashes travel with every session.
5. Automation allocation policy, automation quality, and automation failure mode are independently specified and logged.
6. Negative, null, and non-equivalent qualification results are preserved.

## Product architecture

The repository evolves into interoperable components behind versioned contracts:

- `matb-contracts`: component manifests, experiment specifications, scientific events, timing observations, bundles, automation policies, and qualification evidence.
- `matb-runtime`: deterministic classical MATB task execution.
- `matb-research`: metrics, scenario compilation, study design, analysis, and exports.
- `matb-console`: offline-first experiment design, administration, monitoring, and audit UI.
- `matb-physiology`: LSL/XDF/BIDS synchronization and physical timing qualification.
- `matb-automation`: task allocation policies and explicit failure models.
- Optional `suas`, `liftoff`, and `SMS` components that cannot be required by the open research core.

## Delivery tracks

### Stable evidence track

- Versioned, backward-compatible contracts and migrations.
- Deterministic reference sessions and runtime conformance.
- Fail-closed release gates for timing, calibration, reliability, comparator characterization, licensing, and privacy.
- Citable, checksummed, component-licensed releases and public reference data.

### Experimental innovation track

- Adaptive automation and explicit reliability/failure models.
- Visual deterministic timeline editor.
- SAGAT and unified workload/probe framework.
- Multimodal physiology profiles and advanced analytical derivatives.

Experimental features remain clearly labeled until promoted through the stable evidence gates.

## Phased implementation

### Phase 0 — truthful boundaries and executable contracts

- [x] Synchronize to the latest merged `origin/main` baseline.
- [x] Establish the unchanged scientific and OpenMATB test baseline.
- [x] Implement `ScientificEventV3` and `TimingObservationV1` with deterministic identity and strict validation.
- [x] Implement `ComponentManifestV1` and a capability registry.
- [x] Implement `ExperimentSpecV1` and canonical serialization.
- [x] Make the exported public core importable and testable without optional product trees.
- [ ] Publish component-level licensing and dependency provenance.

Component licensing is now path-mapped and tested; the dependency SBOM remains
part of the controlled release work and therefore keeps the combined item open.

### Phase 1 — measurement kernel

- [x] Introduce a monotonic experiment clock and batch dispatch of every due event.
- [x] Record dispatch start/end separately from scheduled time.
- [x] Add a bounded asynchronous recorder with explicit backpressure/drop evidence.
- [x] Move LSL publishing behind an independently observable sink.
- [x] Add explicit target and non-target SYSMON opportunities with stable IDs and response windows.
- [ ] Expand golden conformance from compiler output to full runtime event behavior.

### Phase 2 — lab-grade research workflow

- [x] Compile canonical experiment specifications into deterministic scenario manifests.
- [ ] Add a visual timeline editor that shows event rates, overlap, refractory intervals, opportunities, probes, and automation periods.
- [ ] Create auditable offline study/session management and encrypted participant-data storage.
- [ ] Add immutable `ResearchBundleV2`, Parquet derivatives, BIDS sidecars, and event-ID reconciliation with LSL/XDF.

The first visual editor tranche is implemented with canonical compilation,
task lanes, event-rate/overlap summaries, explicit SYSMON opportunities,
constraint feedback, and provenance hashes. Refractory visualization and
participant-facing automation-period authoring remain open, so this item is not
prematurely marked complete.

### Phase 3 — adaptive automation beyond USAARL

- [x] Separate allocation policy from automation quality and failure model.
- [x] Support scheduled, offered, requested, threshold-triggered, and forced handoffs.
- [x] Model detection probability, false alarms, latency distributions, bias, control noise, and availability independently.
- [ ] Record every policy input, decision, action, failure realization, and handoff consequence.

Phase 3 is implemented as an experimental, pure Python decision/audit layer. It
hash-chains proposals, actions, handoffs, and linked consequences. No-action
policy evaluations and quality-model realizations are not yet linked into that
chain, so the complete-audit item remains open. The layer must still be integrated
with participant-facing runtime controls and promoted through independent evidence
gates before it is described as validated adaptive automation.

### Phase 4 — empirical qualification

- [ ] Characterize visual, audio, and input latency on named rigs using physical instruments.
- [ ] Calibrate LOW/MEDIUM/HIGH in aviation personnel and independently replicate in general adults.
- [ ] Estimate within-session stability, test-retest reliability, learning, and scenario generalizability.
- [ ] Run preregistered cross-implementation characterization against NASA MATB-II and upstream OpenMATB.
- [ ] Publish de-identified reference data, protocols, analysis code, and null/negative outcomes.

### Phase 5 — world-reference release

- [ ] Ship a signed, checksummed, SBOM-backed, component-licensed release.
- [ ] Archive software, schemas, canonical profiles, evidence, and datasets under permanent DOIs.
- [ ] Publish separate software/technology and empirical-validation papers.
- [ ] Promote only capabilities whose evidence-class gates pass.

## Current implementation tranche

This worktree executes Phase 0, the core of Phase 1, and testable Phase 2/3
primitives. Human studies, physical-instrument measurements, access to comparator
implementations, ethics approval, participant recruitment, and DOI publication
are external evidence activities; the repository provides executable protocols,
ingestion paths, analysis, and fail-closed gates without fabricating their results.

## Definition of done for this tranche

- Shared contracts have machine-readable schemas, Python APIs, deterministic serialization, migration boundaries, and behavior-focused tests.
- Optional product components are discoverable capabilities rather than static dependencies of the public research core.
- Runtime records support distinct clock domains and deterministic event identity.
- SYSMON opportunity denominators are explicitly observable.
- Existing scientific and runtime suites remain green, and new behavior has tests that were observed failing before implementation.

## Experimental semantic-review subproject

The [19 September semantic-review plan](2026-09-19-matb-jev-semantic-review.md) adds optional post-session narrative coding. It does not satisfy physical timing, human validation, automation or participant-intervention gates in this roadmap.
