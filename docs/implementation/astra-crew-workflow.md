# ASTRA callsign workflow and confirmed test calendar

Choose an activity → participate in the study → prepare → callsign → start.
CUELLAR, COLORADO, ICEMAN, WHITE and PIRATA share the same four test dates.
There are no participant passwords, PINs or manual assignment forms.

## Calendar confirmed on 2026-10-06

| Jornada | Bogotá date | Required activities |
| --- | --- | --- |
| DM3 | 2026-10-07 | OpenMATB, sUAS, Pruebas, KSS + PVT |
| DM7 | 2026-10-11 | OpenMATB, sUAS, Pruebas, KSS + PVT |
| DM11 | 2026-10-15 | OpenMATB, sUAS, Pruebas, KSS + PVT |
| Postmisión | 2026-10-20 | OpenMATB, sUAS, Pruebas, KSS + PVT |

These are three mission opportunities, four days apart, plus post-mission.
The earliest incomplete jornada remains current until all four activities are
saved. Completing only one activity never advances the jornada. Future
jornadas open at midnight Bogotá; late work stays pending on its original
jornada instead of being silently skipped. Fixed calendar dates do not slide
when work is late. After post-mission completion no fifth jornada is created.

OpenMATB retains three 15-minute blocks, workload ratings and two 180-second
intervals. KSS + PVT is shared with the same jornada's sUAS prerequisite and is
never duplicated. Retries preserve the prior attempt, cause and frozen limits.
Polar H10 is standalone and optional throughout.

## Existing data and deployment

The v2 calendar uses internal Visit ordinals 9–12, leaving historical V0–V7
visits, dates, results, participant identities and assignments untouched. The
participant sees DM3/DM7/DM11/Postmisión, never these internal numbers. Earlier
practice or a different protocol is not relabeled as a completed test day.

Enable `matb-openmatb` and `matb-suas`. After updating source/build, a named
operator applies the configuration once, and again after executable bindings
change. No active acquisition can be interrupted by configuration. Started
assignments retain their original frozen version; only unstarted assignments
in this calendar may be amended.

```powershell
$configuration = @{
    actor = 'Nombre del investigador responsable'
    reason = 'Calendario confirmado: DM3, DM7, DM11 y postmisión; todas las pruebas por jornada.'
} | ConvertTo-Json
Invoke-RestMethod 'http://127.0.0.1:8000/astra/crew/configure' -Method Post `
    -Headers @{ Origin = 'http://localhost:3100' } `
    -ContentType 'application/json; charset=utf-8' `
    -Body ([Text.Encoding]::UTF8.GetBytes($configuration))
```

This also creates the five callsign folders and their four planned day folders.
The crew enters `/start` or `/study/join?experiment=openmatb&purpose=study`;
other activities are `suas`, `screen` and `pvt`.

## Flat local exports

The default root is repository-relative `exports/`, independent of the launch
directory. `MATB_CREW_EXPORT_ROOT` can select another local root.

`exports/CUELLAR/2026-10-07_DM3/CUELLAR_20261007T083000000000-0500_pvt_<attempt-id>.csv`

The folder uses the observed acquisition day in Bogotá and the jornada code;
the timestamp contains UTC offset -0500. Attempt IDs prevent collisions and
keep retries separate. UTF-8 BOM supports Windows spreadsheet programs.
If preparation is cancelled before acquisition, the folder uses the cancellation
date and `started_at` remains empty; interruption is never counted as completion.
The long-form CSV columns are callsign, participant_id, jornada, planned_date,
test_date, started_at, instrument, attempt_id, attempt_number,
acquisition_state, source_type, source_id, field and value. Arrays and metrics
are flattened to paths such as `raw_trials[0].rt_ms`; they are not JSON blobs.
Native CSV cells are preserved with their original row/column positions;
workload ratings have their own questionnaire attempt CSV. The immutable
native evidence bundles and sUAS recordings remain in their original stores.

A durable export job is recorded in the same transaction as acquisition
completion/interruption. The worker writes only after commit and when no
acquisition is active. A reserved but idle station can export. Deferred sUAS
metrics refresh the derived CSV after finalization. Files are written
atomically; a failed refresh preserves the previous CSV and source records.
Errors appear in station job status. Only whitelisted evidence fields are
exported, excluding credentials and host paths. Practice and legacy visits
remain in their original stores; no outcomes are fabricated for empty folders.

To regenerate copies after a local export failure:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/astra/crew/exports' -Method Post `
    -Headers @{ Origin = 'http://localhost:3100' }
```

Exports, operational databases, backups and verification captures remain local
and excluded from Git.

## Interface specification

Retain the accepted charcoal background (#0b0c0d), white/gray typography, cyan
accent (#00baff), slim header, three-step indicator, five callsign buttons and
two-column selector. Stack the columns on mobile. This is a functional update
inside the existing design system; a new visual concept is unnecessary.

Intentional copy/content changes requested by the user: the jornada and date
replace the generic session number; four activity rows show saved/pending
status; one primary action continues the pending activity; the next date,
days remaining and four-date calendar appear below. No new administrative
form, password, PIN, Polar prerequisite or participant identifier is exposed.

## Verification — 2026-10-06

- 13 isolated crew ledger tests: all four dates, Bogotá midnight, completion of
  every activity before advancing, no fifth jornada, independent participants,
  retries, prerequisite sharing, identity/history preservation and native preflight.
- 7 export tests: flat PVT/raw values, actual versus planned dates, atomic refresh,
  durable commit/rollback, acquisition exclusion, all callsign folders, native
  source boundaries and mission event/rating/metric copies.
- 32 station admission and request-validation regression tests; 18 frontend tests.
- Production build/TypeScript, ESLint and bilingual documentation checks.
- Playwright Chromium fallback (no local Browser/IAB tool available): all five
  callsigns across four activity routes against an isolated real backend; the
  four-day notice and callsign-preserving navigation in a synthetic future state.
  No operational acquisition was started for verification.
- Desktop 1506 × 1045 (the accepted reference size) and mobile 390 × 844;
  no horizontal overflow or browser JavaScript errors. Full-page captures retain
  the additional requested content below the first viewport.

Visual fidelity review used view_image on the accepted reference and final
browser captures. The comparison covered (1) charcoal/white/cyan palette,
(2) heading and callsign typography, (3) slim header and three-step indicator,
(4) two-column spacing, selector and single primary action, (5) open activity
rows without nested cards, and (6) mobile stacking and readable date wrapping.
The next-date notice was moved above the activity list to remain visible in
the active desktop viewport. The copy differences are the requested dated
jornadas, completion list and next-date notice; the existing design system is
retained. No material visual mismatch remains. Physical full-length acquisition
and participant outcomes were not simulated as real study evidence.
