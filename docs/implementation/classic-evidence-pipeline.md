# Authoritative classic MATB evidence pipeline

This pathway connects native scientific capture, immutable ingestion, source
reconciliation, existing metric calculations, inspection, and offline export.
It covers classic OpenMATB. Mission presentation, physiological acquisition,
arbitrary protocol design, and the Replay Studio remain separate extensions.

## Use the Console

New suites prepared through **OpenMATB** register complete native captures
automatically. Each launch has a durable block-attempt UUID, including repeated
practice. Finished blocks are queued; derivation runs after the suite terminates
and no native task or preview is active. The completion receipt links to
`/evidence?session=SUITE_ID&purpose=all` and separates native files, browser
ratings, legacy CSV import, scientific processing and qualification. Failed
processing can be retried with the suite's controller credential. Browser
ratings are never inserted into the immutable native scientific event stream.

After a backend restart, a surviving native process must be closed before
queued derivation or another launch can proceed. Upgrade between sessions.
Historical sessions without attempt records show unavailable detail explicitly;
they are not automatically reprocessed or upgraded.

For captures acquired outside this managed suite flow, manual import remains:

1. Run a native block using the current runtime and its bound scenario manifest.
   See [scientific capture](classic-scientific-capture.md) for the output files.
2. Register its pseudonymized participant and visit in the Console when the
   capture contains that identity.
3. Open **Upload data**, select **Scientific evidence v3**, and upload the capture
   manifest, archived scenario manifest, scientific events, and timing
   observations. Optionally include the companion CSV in this first upload.
4. Inspect the returned findings and metrics, or reopen the capture under
   **Researcher tools → Scientific evidence**. Study, practice and exploration
   captures have separate list filters.
5. Select a metric to inspect its definition/version, value, exclusion reasons,
   original source events, and linked timing observations. Source records are
   paginated and can be filtered by event ID. Exact source text and decimal
   timestamp strings preserve values beyond JavaScript's safe integer range.
6. Export the checksummed evidence bundle. Eligible metrics can also be explicitly
   selected for a frozen, downloadable analysis input. This does not launch an
   automatic three-level model.

The older CSV upload remains available and retains its existing limitations.
Historical results are not upgraded by the new importer or calculators.

## Interfaces and storage

`POST /ingest/evidence` accepts multipart fields `capture_manifest`,
`scenario_manifest`, `events`, `timing`, and optional `legacy_csv`. It returns 201
for a new capture and 200 for byte-identical re-upload. A changed artifact set or
conflicting content under the same capture identity returns 409. Malformed
contracts, unsupported versions, incomplete JSONL lines, and integrity failures
return 422; oversized requests return 413. Source bytes are retained in SQLite
artifact records; uploaded filenames are not filesystem destinations.

Structurally valid captures with scientific defects are stored and receive
explicit reconciliation findings. Derivation runs have `pending`, `succeeded`,
`not_applicable`, or `failed` outcomes where applicable. An unexpected processing
failure retains the capture and records a failed attempt. Startup marks pending
attempts interrupted. `POST /evidence/captures/{id}/reconcile` creates a new run;
it does not edit the original evidence or previous calculations.

Read interfaces:

- `GET /evidence/captures?purpose=study&offset=0&limit=25`: lightweight discovery summaries; also accepts `purpose=all`, exact parent suite `session`, and literal search `q`. Dates indicate Console registration time.
- `GET /openmatb/sessions/{id}/receipt`: durable per-attempt save/processing outcomes.
- `POST /openmatb/sessions/{id}/blocks/{block_instance_id}/evidence/retry`: retry queued native evidence with the controller lease after suite termination.
- `GET /openmatb/displays`: current native display order, dimensions and position; preparation and launch independently revalidate the selected index.
- `GET /evidence/captures/{id}`: provenance, attempts, findings and metric results.
- `GET /evidence/captures/{id}/records`: `stream=events|timing`, optional `task`,
  `event_id`, `metric_id`, and pagination; maximum page size 200.
- `GET /evidence/captures/{id}/metrics/{metric_id}`: one calculation result.
- `GET /evidence/captures/{id}/export`: reproducible evidence ZIP.
- `POST /evidence/analysis-inputs` with `{"metric_ids":["..."]}`: freeze explicit
  eligible study results. `GET /evidence/analysis-inputs/{fingerprint}` retrieves
  the immutable selection.

New tables are additive. Legacy `Block` uniqueness, `/metrics/long`, and existing
analysis inputs remain unchanged. The new input fingerprint includes source
hashes, calculation definitions/version, reconciliation and eligibility. Repeat
block instances do not collide with visit/workload cells. Suhir is explicitly
`not_applicable` because this pathway has no protocol-declared model inputs.

## Reconciliation and eligibility

Reconciliation checks event IDs/order, capture/session/block/source identity,
the runtime's original scenario-manifest binding, planned opportunity counts,
actor/allocation evidence, task lifecycle, sample coverage and questionnaire
completeness. Duplicate or orphan observations, regressions and dispatch failures
are explicit findings. Missing values are not filled from CSV, inferred from
elapsed time, or interpolated. Companion CSV is a compatibility cross-check.

Shared calculators retain the existing formulas and metric schema 2.0. Eleven
Console metrics span SYSMON, tracking, resource management, communications,
NASA-TLX, Bedford and ISA. Unsupported weighted TLX is not fabricated. Absent
tasks/probes are `not_applicable`; a broken task stream does not automatically
invalidate unrelated complete task evidence. Capture-level integrity or lifecycle
defects exclude all affected results.

Continuous samples must form complete pairs inside recorded active intervals.
The version-1 coverage rule flags gaps greater than three declared update
intervals, including interval boundaries. Resource-management target tanks must
be represented. This is a versioned software completeness rule, not a physical
sampling qualification. Unknown or automated allocation excludes human task
performance metrics.

Metric `status` describes derivation; `confirmatory_eligible` describes the
existing metric contract's evidence requirements. Excluded descriptive values
may remain visible with their reasons. Valid source reconciliation does not
establish physical onset or human validity. COMM remains non-confirmatory
without physical audio-onset qualification. Dirty/missing source provenance and
practice/exploration purpose remain explicit exclusions. Hardware qualification
and human calibration remain separate from source-contract eligibility. New
capture-level qualification links retain reviewed reports and invalidations;
unlinked captures display `not_qualified`.

## Reproduce an export

The ZIP contains the exact uploaded sources, a report with source links and
calculation metadata, and checksums. With this implementation installed:

```console
python -m matb_integration.evidence evidence-CAPTURE_ID.zip
```

The verifier reads bounded ZIP members without extracting them, validates all
checksums, recomputes reconciliation/metrics, and compares the fingerprint and
reported values. It makes no network requests. Store source code and dependency
versions with a pinned release; a ZIP alone is not a portable Python environment.

Reference fixtures are explicitly synthetic and test software only. Never treat
their P01 identifier, fixed source IDs, scores, or timing as participant data.

## Verification and release gates

The implementation includes native emission/failure tests, contract/metric
regressions, task-subset and interruption tests, integrity/identity and missing
actor/sample/observation tests, backend re-upload/recovery/export tests, and a
browser upload-to-offline-export acceptance test. CI retains test reports and
browser evidence on Windows and Ubuntu when jobs can run.

The local browser run uses synthetic records. Software checks do not complete
the clean-machine Linux release gate, GPU/display timing qualification, human
calibration, or physiological synchronization. GitHub Actions had a confirmed
account billing/spending restriction before this work; changing workflow code
cannot remove that restriction. Report remote CI separately from local results.

The complete pathway was subsequently consolidated into `main` and checked in
isolated Windows and Linux environments; see the
[integration verification](../reports/evidence-integration-verification-2026-09-09.md).
Analysis provenance, qualification links, event review and capacity measurements
are described in the [follow-up implementation](evidence-review-qualification-performance.md).

See the [original dated local verification report](../reports/classic-evidence-verification-2026-09-09.md)
for observed test results, the browser evidence and remaining release gates.

## Optional experimental semantic review

See [semantic review](semantic-review.md) for the separate default-off inference ledger. Its assessments are excluded from scientific metrics and frozen metric selection.
