# ASTRA participant workflow

Requested on 2026-10-06: participant → activity → study → prepare → callsign →
start. Callsigns: CUELLAR, COLORADO, ICEMAN, WHITE, PIRATA. No participant
passwords or PINs. Polar remains a separate optional activity.

## Visual specification

The participant screen follows the generated desktop reference and uses a charcoal background
(`#0b0c0d`), white text, muted gray (`#a1aab4`), cyan (`#00baff`), 6–10 px corner
radii, a slim MATB · ASTRA header, and a centered 1120 px content area. A
three-step indicator precedes a mixed-case question and the activity name.
Five large callsign buttons occupy the left column; the right column presents
the pending session and a single primary start action. On narrow screens the
columns stack. No administrative sidebar, version IDs, assignment arms, or
physiology controls appear in this participant surface.

The reference's CUELLAR / Sesión 2 is illustrative. Actual selection and
progress come from persisted records; loading, interruption, saved-today,
rest-interval, unavailable, and all-complete states use the same visual system.
Selection is explicit; starting an activity requires the primary action.

## Operational rules

- Preserve participant IDs, results, prior assignments, and frozen versions.
- Apply the simplified configuration prospectively through a named, recorded
  configuration action. Started assignments retain their original version.
- Choose the earliest incomplete session for each participant and activity.
  Permit at most one completed session per activity per Bogotá calendar day.
  Preparing, refreshing, or interrupting an attempt does not complete a day.
- Reuse an unstarted attempt, preserve interrupted attempts, and record a
  bounded retry according to the frozen repeat policy. Never skip an active
  attempt or relabel practice as study evidence.
- Keep the existing task durations, scoring, workload questionnaires and
  between-block intervals. The native hardware preflight still runs before
  releasing OpenMATB. Missing KSS + PVT for sUAS is opened directly.
- Resolve visits, arms, prerequisites and internal session tokens automatically.
  Participant codes and tokens are not login inputs.
- Polar acquisition is never a prerequisite or automatically started by this
  flow. Existing physiological recordings remain historical records.

Validation includes progression and midnight boundaries, repeat/concurrency
guards, roster identity preservation, no Polar dependency, the selected
activity's destination, browser task saving, and desktop/mobile rendering.

## Deployment and verification — 2026-10-06

The station must enable `matb-openmatb` and `matb-suas`. A named operator calls
`POST /astra/crew/configure` with `actor` and `reason` once when installing this
workflow, and after executable bindings change. This creates a prospective
version and amends only unstarted assignments; participant GET/start requests
never freeze a study or attest to consent. The crew enters through `/start` or
`/study/join?experiment=openmatb&purpose=study`. Other activity values are `suas`,
`screen` and `pvt`. Internal session credentials are stored automatically in the
current tab, with no participant password/PIN fields.

For example, from PowerShell after the station is updated:

```powershell
$configuration = @{
    actor = 'Nombre del investigador responsable'
    reason = 'Activación autorizada del recorrido ASTRA por callsign y sesión pendiente.'
} | ConvertTo-Json
Invoke-RestMethod 'http://127.0.0.1:8000/astra/crew/configure' -Method Post `
    -Headers @{ Origin = 'http://localhost:3100' } `
    -ContentType 'application/json; charset=utf-8' `
    -Body ([Text.Encoding]::UTF8.GetBytes($configuration))
```

Each daily OpenMATB session includes three 15-minute blocks, their workload
ratings and two 180-second intervals. The day's limit applies after the entire
activity session is complete, not after its first block. Practice never counts
as a completed study session. Instructions and response timing remain in the
canonical task components. Selecting another crew member closes an idle prior
reservation automatically; it cannot stop an acquisition. An explicit retry can
recover only this assignment's already-interrupted browser attempt. Native
process ownership remains protected. Legacy practice attempts whose underlying
native source is terminal do not block deployment; their records are untouched.

Completed checks:

- 12 isolated backend tests: callsigns, identity preservation, prospective
  configuration/idempotence, double-click reuse, Bogotá midnight, independent
  activities, prerequisite retries, admission/ownership, native ratings/rest,
  idle crew changes, preservation of terminal historical practice records and
  creation/reuse of the assigned native session up to hardware preflight.
- 16 frontend tests: activity routing, explicit callsign selection, daily limit,
  native preflight/release sequencing, real-context KSS response, full-length
  PVT/screen payloads, failed-save retry and one-time sUAS start on connection.
- Production build, including TypeScript checking.
- Playwright against the compiled application: requested participant entry,
  real server roster, five callsigns, selection, desktop at 1506 × 1045 and
  mobile at 390 × 844 without horizontal overflow. Browser acquisition was not
  started against the operational database. All four activity selectors and the
  home shortcut passed on the final build, with no browser JavaScript errors.
- Local native readiness returned `ready: true`, with installed runtime,
  Spanish questionnaires and graphical displays. A full physical acquisition
  with audio/controller responses remains an operator check.
- Verified an operational backup before local configuration and checked that
  existing acquisition records were preserved. Verification generated no study
  outcomes. Operational records and backups are excluded from this change.

Visual comparison with the generated reference passed on: (1) charcoal surface
and slim header, (2) centered three-step indicator with cyan active state,
(3) title/activity hierarchy, (4) five large left-column callsign buttons with
visible selection, (5) right-column session details and one cyan primary action,
and (6) consistent spacing and readable contrast. Mobile stacks the same two
columns. The reference's illustrative “Sesión 2” is replaced by the persisted
pending session, rather than a fixed demonstration value.

The design reference and final desktop/mobile captures were opened and
inspected, and are retained locally as verification artifacts. They are not
participant study outcomes.
