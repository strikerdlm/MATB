# Classic MATB scientific capture v1

The native runtime now emits the existing `ScientificEventV3` and
`TimingObservationV1` envelopes. These are additional streams; historical CSV
and `*.events.jsonl` retain their original meanings. In particular, the older
runtime envelope still says `not_scientific_event_v3`.

| Artifact | Meaning |
| --- | --- |
| `*.csv` | Compatibility recording, with the existing six-decimal rounding |
| `*.events.jsonl` | Existing ordered runtime envelope |
| `*.scientific.events.jsonl` | Scientific events with stable identities and native values |
| `*.timing.observations.jsonl` | Event-linked software observations in named clocks |
| `*.scenario.manifest.json` | Exact archived scenario manifest bytes |
| `*.capture.manifest.json` | Capture identity, completion, stream hashes/counts and provenance |

The capture manifest starts with `recording` and is atomically replaced when
sealed as `completed`, `interrupted`, or `failed`. An unfinished manifest after a
process or storage failure is evidence of an incomplete capture. It must not be
manually relabelled as complete. The logger stops measured execution if a
scientific sink fails or reaches capacity. No missing events are synthesized.

## Identity and task records

Each native block has its own session UUID and block-instance UUID. The Console
launcher also binds its parent session, participant, visit ordinal, condition and
study/practice purpose. A practice block remains practice even inside a study
suite. Direct native launches default to exploration; source commit and dirty
state are inspected at launch. Missing/dirty provenance remains provisional.

The launcher's `MATB_EVIDENCE_IDENTITY` JSON supplies the parent identity. This is
metadata for the recorder, not a task or scoring control. The session manifest
must agree with the uploaded scenario identity. A capture ID is derived from the
native session UUID and cannot be changed to re-import the same session as a new
capture. Separate native sessions can repeat the same condition.

`classic-runtime-payload-v1.schema.json` defines the native payload carried by
the scientific envelope. The event catalogue is:

- `block.started`, `block.completed`, `block.interrupted`: capture lifecycle.
- `<task>.task.started/stopped/paused/resumed`: task observation intervals.
- `sysmon.opportunity.opened/closed/rejected`: target/non-target lifecycles.
- `communications.opportunity.opened/presentation_started/response_window_opened/closed/invalidated`:
  communication lifecycles.
- `<task>.automation.changed`, `<task>.input`, `<task>.sample`,
  `genericscales.probe`: allocation, inputs, measurements and subjective items.
- `runtime.record`: other native records, including parameter and failure evidence.

Opportunity UUIDs are derived from native session, task and original opportunity
ID. Original IDs and values remain in the payload. The recorder observes
allocation and sampling interval at the measurement call. It also retains the
CSV projection for compatibility comparison without rounding scientific values.

## Timing and failure boundary

Software receipt uses a direct `perf_counter_ns()` observation at the native
logger boundary. Existing scenario-dispatch start/end observations retain their
actual boundaries. Scheduled observations use the scenario clock. Their values
must not be subtracted across clock domains without a qualified mapping.

No photodiode, physical input, physical audio-onset, or physiological
synchronization claim is added. The capture contracts permit independently
qualified observations; emitting software records alone does not qualify them.
The recorder adds synchronous validation and writes whose overhead must be
measured on the intended rig before research qualification.

Per scientific stream, the recorder/importer limit is 256 MiB and 500,000
records; one JSONL record is limited to 256 KiB. The limits are explicit failure
boundaries, not an adaptive sampling policy. Recording never silently drops
samples to fit them. The runtime requires Pydantic 2; install the repository's
current native requirements on a clean workstation.

Evidence ingestion and metric inspection are delivered by the dependent Console
change. Hardware timing, human calibration, and protocol-specific interpretation
remain independent qualification work.
