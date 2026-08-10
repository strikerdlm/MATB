# Research data dictionary

This dictionary describes the boundary for the FAC ISR human-factors research
store. It is intentionally separate from the operational SMS and mission
stores. Research mode is always non-dispatchable; a research session or event
must never be copied into a mission release, qualification, or fitness status.

## Identity and governance

| Field | Meaning | Boundary |
| --- | --- | --- |
| `protocolId` / `version` | Approved research protocol and revision | Must match the current ethics approval. |
| `ethicsApprovalId` | Ethics approval record | A session can start only inside the approval window. |
| `investigatorId` | Accountable investigator reference | Research governance only; it is not an operational user ID. |
| `participantCode` | Pseudonymous participant identifier | No name, personnel number, call sign, or operational user ID is stored here. |
| `consentVersion` / `consentedAtUtc` | Version and time of informed consent | Consent must precede the session; withdrawal is retained as provenance. |
| `conditionAssignment` | Experimental condition label | Contains no dispatch or qualification decision. |
| `retentionDays` | Approved retention period | Deletion and withdrawal follow the protocol’s approved policy. |

## Session and event fields

`ResearchSession` contains an opaque session ID, protocol and ethics references,
participant code, condition assignment, UTC start/end timestamps, an immutable
`nonDispatchable: true` marker, and research events. A `ResearchEvent` contains
an event ID, session ID, UTC timestamp, monotonic sequence, event type,
research payload, and a quality flag (`valid`, `degraded`, or `rejected`). Its
`dataDomain` is always `research` and its `nonDispatchable` marker is always
`true`.

Payloads are limited to protocol-approved instrument, sensor, task, timing, and
quality variables. Unknown fields that could cross the operational boundary
(for example `operationalUserId`) are rejected by the contract parsers.

## Instruments and sensors

The controlled templates are SAGAT, NASA-TLX, ISA, Bedford workload, and SART.
Every response records the instrument ID, approved version, administration time,
validated values, and a missingness reason when a value is absent. MATB, HRV,
eye-tracking, and psychomotor inputs are research-only adapters; they do not
write operational qualification, release eligibility, or medical records.

## Approved uses

Individual-level exports are deidentified and contain participant codes only.
Findings may be used for training, interface change, or SMS assurance only
through an approved aggregate review with documented cell-size and limitation
controls. No research response automatically changes a person’s operational
status.
