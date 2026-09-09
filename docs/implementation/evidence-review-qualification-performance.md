# Evidence review, qualification links and measured performance

The complete classic scientific capture/reconciliation/inspection/export pathway
is on `main` through [PR #65](https://github.com/strikerdlm/MATB/pull/65).
This extension records analysis implementation identity, links qualification
reports, provides event-linked task review, and reduces measured storage and
scene-object overhead. It preserves the classic/mission instrument boundary.

## Separate acquisition and analysis identities

New reconciliations use `classic-evidence-1.1`. `analysis_execution` records:

- The actual analysis checkout commit and tracked modification status, independent
  of the acquisition manifest's `source_commit` and `MATB_SOURCE_COMMIT` variable.
- Normalized source-file SHA-256 hashes and their aggregate implementation hash.
- `requirements-evidence.lock` SHA-256, installed analysis dependency versions,
  and whether those versions match the lock.
- Python, OS and machine architecture, plus the fixed analysis configuration
  (three-interval completeness rule; no missing-value interpolation).

This context participates in the reconciliation fingerprint and frozen analysis
inputs. The lock pins the minimal offline calculator, not the entire Console or
acquisition environment. Distributions without Git retain unavailable commit
metadata; source hashes remain inspectable. The tracked-dirty flag makes no claim
about untracked files.

The explicit `classic-evidence-1.0` reader retains its original fingerprint and
calculations. Old exports are not assigned invented execution metadata. Offline
verification checks source bytes, values, links and fingerprint, then reports its
own implementation/environment and whether these match the recorded analysis.
Recalculation in another environment does not establish identical execution
conditions. Checksums establish consistency, not authorship signatures.

```console
python -m pip install -r requirements-evidence.lock
python -m matb_integration.evidence evidence-CAPTURE_ID.zip
```

## Linked qualification evidence

Append-only records bind an exact context: rig, OS, display, input, audio,
acquisition, presentation, software versions, protocol and protocol version.
Each includes reviewer, assessment time, assessment, checksummed attachments,
and invalidation conditions. A changed context requires a new record. Revocation
is appended and invalidates existing links to that report.

Physical timing reports use the existing qualification evaluator and must
describe the same rig. Human calibration retains a reviewed external study report
and its stated method/result. Neither operation changes metric
`confirmatory_eligible` or automatically validates a participant population.

Existing capture manifests lack the full rig context. A link therefore requires
`context_source: "reviewer_attestation"`, reviewer and rationale; it verifies the
available acquisition commit, visual profile and capture-manifest hash. It does
not claim automatic rig acquisition. Protocol eligibility stays a separate,
unassessed decision.

| Operation | Research Console endpoint |
| --- | --- |
| Register immutable report | `POST /evidence/qualifications` |
| Inspect report/revocations | `GET /evidence/qualifications/{record_id}` |
| Revoke with reviewer/reason | `POST /evidence/qualifications/{record_id}/revoke` |
| Link exact report/context | `POST /evidence/captures/{capture_id}/qualifications` |
| Inspect separate outcomes | `GET /evidence/captures/{capture_id}/qualifications` |

These use the existing local deployment/access boundary. Request schemas are in
`matb_integration/evidence/qualification.py`. Attachments have safe member names,
individual checksums, a combined decoded limit of 8 MiB and maximum of eight per
report. A capture permits 32 links. The inspector displays report IDs, reviewers,
outcomes and invalidations. Exports include attachments; offline verification
checks their checksums, identities, bindings and status. The fixture in
`test_evidence_qualification.py` deliberately reports `NOT_MEASURED`; it is not
laboratory qualification evidence.

## Result-to-event review

The inspector groups readable metric names by task, formats units and display
precision, retains exact values/definitions, and explains common exclusions
alongside machine codes. Capture status distinguishes pending, processing
failure, partial exclusion and reconciliation. Qualification remains separate.
Narrow screens switch between results and evidence.

Select a source event to inspect its opportunity sequence and linked observations:

`GET /evidence/captures/{capture_id}/events/{event_id}/context`

The view is bounded to 32 opportunity records, 32 preceding task records and 128
linked timing observations. The selected event stays in the window. Ambiguous
identities are rejected; truncation is explicit. Original JSON and decimal
timestamp strings are preserved. Clock domains are shown rather than subtracted
without a qualified mapping.

This first event-linked task review does not reconstruct original native pixels.
Native visual exposure, physical onset, gaze and synchronized physiology are
explicitly unavailable. Mission replay remains its own presentation adapter.
Cross-session comparison, reviewer annotations and physiological tracks require
further implementation and synchronization evidence.

## Storage and process ownership

Identical re-uploads hash and compare immutable artifacts before reparsing them.
New captures still undergo full schema, integrity and count validation.
Metric-source indexing flushes batches of 500. HTTP export writes a temporary ZIP
through SQLite incremental BLOB reads and streams 1 MiB chunks; cancellation and
completion close the temporary file. Source hashes are checked while writing.

Parsing and derivation still hold complete source/event structures; disk-backed
export does not eliminate ingestion peak memory. The export report/source-link
list remains materialized. The offline verifier also reads bounded members into
memory. Capacity reports describe these remaining costs.

Use one backend worker for this SQLite store and experiment runtime. The existing
backend lease enforces ownership; the derivation lock is process-local. Multiple
workers require coordination of derivation, acquisition ownership and recovery.
Interrupted indexing rolls back; startup marks pending derivations
`interrupted_processing`.

## Mission rendering policy

Continuous interpolation lives in the Three.js adapter or isolated SVG map.
The parent Console receives discrete authoritative snapshots; commands use that
authoritative state. Interpolation changes positions and headings only. Aircraft,
contacts and routes have separate keyed registries. Coverage changes do not
recreate boundaries or aircraft. Hidden/redacted contacts cannot retain visible
or clickable markers.

Pinned `interpolation_policy` is `linear-320-v1` (existing behavior) or `none-v1`.
New resolved records carry the policy and effective 0/320 ms duration. Reduced
motion, freeze, disconnection and replay suppress live interpolation; old records
can omit these additive fields. The backend rejects policies outside the session
condition. This policy is not a measured transport or physical display latency.

Invalidations are coalesced into one pending frame submission. Interpolation and
camera transitions own bounded animation; idle scenes have no permanent loop.
Lifecycle counters expose object creation/disposal. Renderer duration remains CPU
submission/label work. GPU completion and physical onset are `null`. Study quality
is not automatically reduced, and authoritative task behavior is unchanged.

## Repeat the software measurements

Use an unused output directory; tools refuse to overwrite previous runs.
Capacity mode requires backend dependencies and its directory on `PYTHONPATH`.

```console
python -m matb_integration.evidence.benchmark recorder OUTPUT --samples 1000 --interval-ms 2 --repeats 3
python -m matb_integration.evidence.benchmark capacity OUTPUT --samples 18000
python -m matb_integration.evidence.benchmark capacity OUTPUT --samples 3000 --payload-bytes 85000
```

Use `--reuse-source PREVIOUS_OUTPUT/source` for byte-identical before/after
capacity comparisons. From `webui/frontend`, run
`node scripts/benchmark-operational-scene.mjs OUTPUT.json` for the bounded object
CPU benchmark. None measures physical input or display onset. The recorder stays
synchronous; compare results with prespecified rig/protocol limits before
changing its buffering model.

See the [measurement report](../reports/evidence-performance-2026-09-09.md) and
[integration verification](../reports/evidence-integration-verification-2026-09-09.md).
Physical timing, human calibration, a preregistered visual-condition study and
cross-condition shadow-mode model validation require actual external evidence.
