# ASTRA Liftoff Pilot Acceptance Record

**Status:** Template — not acceptance evidence

**Protocol:** `astra-2026`

**Required cohort:** At least four de-identified pilot users × three sessions

Do not record names, Steam identities, BLE addresses, clinical diagnoses, or operational clearance decisions here. Retain institutional permission and identifiable source records in the approved private system, outside the code repository.

## Frozen workstation configuration

| Field | Reviewed value / evidence reference |
|---|---|
| Liftoff build | |
| Commercial telemetry profile | |
| Characterization report SHA-256 | |
| Commercial fixture SHA-256 | |
| Track ID and revision | |
| Drone/component configuration | |
| Flight mode; rates; expo | |
| Camera angle; FOV | |
| Controller model; firmware; calibration | |
| Display resolution; refresh; graphics preset | |
| Polar H10 recorder version | |
| MATB commit | |
| HRV commit and contract schema SHA-256 | |
| Written institutional research-use permission location | Private reference only: |

## Telemetry and bundle acceptance

Command:

```powershell
python scripts/run_liftoff_acceptance.py `
  --protocol astra-2026 --duration-min 30 `
  --udp-interruption-recovered `
  --second-machine-checksum-verified `
  --output exports/liftoff-acceptance.json
```

| Criterion | Required | Observed | Pass |
|---|---:|---:|:---:|
| Median telemetry loss | <1% | | ☐ |
| Schema errors | 0 | | ☐ |
| Queue overflows | 0 | | ☐ |
| Clock discontinuity | None | | ☐ |
| Unrecoverable bundles | 0 | | ☐ |
| Intentional UDP interruption recovered | Yes | | ☐ |
| Second-machine checksum verification | Yes | | ☐ |

## Failure cards

For each card, record UTC, de-identified session UUID, expected disposition, observed disposition, artifact/checksum reference, reviewer, and result.

| Card | Expected disposition | Evidence | Pass |
|---|---|---|:---:|
| Polar Bluetooth disconnect | Flight evidence preserved; physiology pending/missing | | ☐ |
| UDP interruption | Quality deviation; recovery remains append-only | | ☐ |
| Liftoff crash/restart | Partial seal; technical retake may be reviewed | | ☐ |
| MATB backend restart | `INTERRUPTED`; no inferred completion | | ☐ |
| Offline Steam operation | Fixed condition remains usable without leaderboard dependence | | ☐ |
| Visible stutter/performance failure | Deviation and affected-run invalidation | | ☐ |
| Forced partial seal | No complete debrief; checksums valid | | ☐ |
| HRV outage then retry | Pending artifact, then authoritative link | | ☐ |

## De-identified calibration sessions

| Pilot code | Session UUID | Visit simulation | Validity | Loss % | HRV link | Track completed | Simulator-sickness event | Notes code |
|---|---|---|---|---:|---|:---:|:---:|---|
| CAL-01 | | 1 | | | | ☐ | ☐ | |
| CAL-01 | | 2 | | | | ☐ | ☐ | |
| CAL-01 | | 3 | | | | ☐ | ☐ | |
| CAL-02 | | 1 | | | | ☐ | ☐ | |
| CAL-02 | | 2 | | | | ☐ | ☐ | |
| CAL-02 | | 3 | | | | ☐ | ☐ | |
| CAL-03 | | 1 | | | | ☐ | ☐ | |
| CAL-03 | | 2 | | | | ☐ | ☐ | |
| CAL-03 | | 3 | | | | ☐ | ☐ | |
| CAL-04 | | 1 | | | | ☐ | ☐ | |
| CAL-04 | | 2 | | | | ☐ | ☐ | |
| CAL-04 | | 3 | | | | ☐ | ☐ | |

## Pilot release thresholds

| Threshold | Required | Observed | Pass |
|---|---:|---:|:---:|
| Pilot users | ≥4 | | ☐ |
| Sessions per user | 3 | | ☐ |
| Median telemetry loss | <1% | | ☐ |
| HRV linkage success | ≥90% | | ☐ |
| Unresolved clock/schema errors | 0 | | ☐ |
| Selected-track completion | 70–90% | | ☐ |
| Severe simulator-sickness events | 0 | | ☐ |
| Second operator completes draft SOP unaided | Yes | | ☐ |

## Decision

- ☐ **PASS:** every threshold and failure card passed; commercial fixture reviewed; institutional permission retained.
- ☐ **HOLD:** unresolved evidence remains. Do not publish the final SOP or update the canonical ASTRA protocol.
- ☐ **FAIL:** one or more safety/integrity thresholds failed. Suspend participant collection and document corrective action.

Reviewer 1 / UTC:

Reviewer 2 / UTC:

Evidence bundle SHA-256:
