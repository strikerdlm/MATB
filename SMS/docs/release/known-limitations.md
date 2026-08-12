# Known limitations and operating boundaries

Release `fac-isr-sms@0.1.0` is **not operationally ready**. Every limitation below is open and release-blocking. The machine-readable source of status and required action is `operational-readiness-record.json`; this document explains the operational meaning.

| ID | Boundary | Required disposition |
| --- | --- | --- |
| `LIM-CAP-001` | Aircraft/platform capability is demonstrated with software fixtures and simulated unarmed ISR/support scenarios; no aircraft installation or compatibility is qualified. | Keep the release in non-operational evaluation. Approve a platform configuration and complete representative hardware-in-the-loop and aircraft-interface acceptance. |
| `LIM-GEO-001` | Institutionally approved terrain and obstacle coverage is not bundled or accepted. | Treat geographic displays as planning context and prohibit terrain/obstacle-dependent release decisions until signed packages and coverage tests are accepted. |
| `LIM-DATA-001` | Official map, AIP, and NOTAM acquisition, currency, reconciliation, and expiry controls are not institutionally accepted. | Missing, expired, stale, out-of-coverage, or unverifiable critical data blocks the affected dispatch or decision. Use only the controlled exception described below. |
| `LIM-TEL-001` | Telemetry field completeness, units, timing, provenance, and failure behavior have not been qualified against a representative aircraft source. | Enter the documented unknown/degraded state for stale, malformed, missing, or conflicting fields; do not use them for flight-critical decisions. Complete signed adapter and hardware-in-the-loop validation. |
| `LIM-PROFILE-001` | The implemented profile is limited to Colombian state-aviation unarmed ISR/support safety monitoring. Civil/commercial approval, weapons, strike, autonomous flight, swarm control, and aircraft command-and-control are outside scope. | Block out-of-profile use and require a separately designed, verified, and institutionally accepted profile for any expansion. |
| `LIM-TRANS-001` | English translations and software summaries have not received final qualified bilingual legal review. | The official Spanish source controls. Do not make a final regulatory determination from English assistance; complete and sign the controlled translation review. |
| `LIM-RES-001` | Research workflows use synthetic or deidentified evidence and are not approved for human-subject or operational decision use. | Keep research data segregated and non-dispatchable; obtain protocol/ethics, privacy, and governance approval before real participant use. |
| `LIM-HF-001` | Automated accessibility tests do not constitute representative operational usability acceptance. | Limit use to evaluation until qualified reviewers complete the approved human-factors protocol with representative users, hardware, and environments. |
| `LIM-SEC-001` | Repository security checks do not replace receiving-site approved scanning, penetration testing, key custody, encryption, and deployment attestation. | Do not deploy operationally until the institutional cybersecurity reviewer and deployment authority sign the exact release evidence. |
| `LIM-PERF-001` | Multi-aircraft and accelerated 12-hour tests are synthetic; they are not wall-clock soak or representative hardware-in-the-loop qualification. | Complete and accept receiving-hardware load, recovery, endurance, and wall-clock soak evidence before operational release. |

## Controlled exception for missing or expired critical data

There is no automatic override. Missing, expired, stale, out-of-coverage, or unverifiable critical data causes the affected dispatch or operational decision to stop. A controlled exception may be considered only when all of the following are recorded:

1. A currently delegated authority identifies the exact mission, data gap, affected functions, and time-bounded exception window.
2. A qualified reviewer verifies alternate official evidence and records its provenance, effective time, coverage, and immutable hash.
3. The risk authority documents residual risk, compensating controls, stop criteria, conditions, and required monitoring.
4. Every required human decision is signed in the institutional system of record and linked to this release evidence.
5. The console continues to display the missing/expired state and the exception; it must not fabricate data, hide uncertainty, or label planning context as official.

If any element is absent or expires, the exception is invalid and the affected activity remains blocked.

## Closure rule

A limitation may be changed to `closed` only after the named human action is complete, the evidence is immutable and hash-addressed, the appropriate institutional review scope is unconditionally accepted, and the release record is independently re-verified. Automated tests may support closure but cannot sign or approve it.
