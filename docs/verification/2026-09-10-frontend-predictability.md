# Frontend predictability verification

Implementation base: `20055cce5e8766541218a7470a49eb7288797488`.
Working branch: `codex/frontend-predictability`.
Plan: [approved implementation sequence](../superpowers/plans/2026-09-09-frontend-predictability.md).

## Implemented behavior

- Explicit practice/study preparation, stored-purpose continuations, persistent purpose badges, per-tab workspace navigation and lifecycle-driven session progress.
- Six deliberately answered workload values, explicit midpoint acceptance, named missing responses, and instrument/session/attempt-bound drafts in sessionStorage. Ratings are cleared only after a matching confirmed save. Original English/Spanish scale wording, anchors, steps and scoring are preserved.
- Readiness first; detected display selection, revalidation, recovery guidance and configuration disclosures. A blocked instructions popup has a visible reopening action. Preparation does not launch the native task.
- Durable native attempts and truthful save receipts. Ratings, legacy import, scientific processing and qualification remain distinct. Automatic immutable evidence processing waits until the suite ends and no native process is active; restart recovery retains this exclusion.
- Searchable evidence discovery and exact capture/parent-session links that persist through reload and browser history. Registration time is labeled as registration time.
- Mission tab keyboard behavior and fixed versioned console feedback, independently recorded from scene presentation. Historical missing profiles retain their legacy appearance.

## Verification record

Completed frontend gates from `webui/frontend`:

| Command | Result |
| --- | --- |
| `npm test` | 68 files, 224 tests passed |
| `npm run lint` | Passed |
| `npm run typecheck` | Passed |
| `npm run build` | Passed; all 29 pages generated |

The combined backend gate includes native records/runtime, migrations, lifecycle,
evidence derivation/review/qualification, and mission runtime/endpoints/failures:

```bash
env PYTHONPATH=/tmp/matb-predictability-testdeps \
  /root/repos/MATB/.venv/bin/python -B -m pytest \
  webui/backend/tests/test_openmatb_records.py \
  webui/backend/tests/test_openmatb_runtime.py \
  webui/backend/tests/test_db_migrations.py \
  webui/backend/tests/test_component_lifespan.py \
  webui/backend/tests/test_evidence.py \
  webui/backend/tests/test_evidence_qualification.py \
  webui/backend/tests/test_evidence_review.py \
  tests/test_evidence_pipeline.py tests/test_evidence_provenance.py \
  webui/backend/tests/test_simulation_runtime.py \
  webui/backend/tests/test_simulation_endpoints.py \
  webui/backend/tests/test_simulation_failures.py -q
```

Result: **107 passed**. A subsequent review repair adds six aborted-debrief cases
(research/technical × current/legacy/unknown profile). Those six plus three
existing restored-profile cases passed in the focused endpoint gate: **9 passed**.
They verify exact recorded identity or historical absence, including restored
sessions, without modifying sealed manifest bytes.

Missing test dependencies were installed in `/tmp/matb-predictability-testdeps`,
keeping the original checkout's environment unchanged. The backend warning was
the existing `python_multipart` deprecation.

## Browser conditions and scope

Chrome with production Next.js output and process-isolated SQLite/artifact roots.
English and Spanish (`en`, `es-419`) at 1280×720, 1366×768, 1920×1080, 768×1024 and
390×844. Actual browser zoom is set to 200% with OS-level Chrome shortcuts in an
isolated Xvfb display; tests verify doubled devicePixelRatio and halved CSS
viewport width. CDP display dimensions are used for zoom screenshots, avoiding
Playwright's cropped CSS-coordinate capture under real browser zoom.

Native-window lifecycle, displays and popup blocking are controlled API/browser
responses in these browser tests. Questionnaire interactions, reload, route
transitions, locale changes and popup reopening use real rendered controls.
Backend tests independently cover native launch identity, interrupted process
recovery, sealed files, idempotent ratings and immutable evidence derivation.
The evidence browser test uploads and exports actual synthetic source records,
verifies the downloaded bundle offline, and exercises capture selection outside
its filtered list plus back/forward and reload.

Completed browser batches:

| Batch | Result |
| --- | --- |
| Native preparation, questionnaire, lifecycle, role and ten locale/size layout cases | 18 passed |
| Actual 200% zoom, failed/historical receipts, Liftoff phase workflow | 5 passed |
| Mission tabs/keyboard, axe, reduced motion, desktop layouts and Spanish technical launch | 7 passed |
| Complete four-block mission/debrief and observer/controller reconnection | 2 passed |
| Catalog/evidence discovery and final keyboard entry checks in both languages | 11 passed |

Together these completed batches cover **41 distinct browser cases**; the last
batch repeats two mission cases to verify ordinary Tab entry into the active tab,
then arrow navigation, activation, panel entry and return. Browser test outputs
are grouped in `native-browser`, `recovery-zoom-browser`, `mission-console-final`,
`mission-lifecycle-final` and `discovery-keyboard-final` under the artifact root.

These run through `npm run test:e2e -- <specs>` with `MATB_PYTHON` pointing to the
existing Python environment and `PYTHONPATH` to the isolated test dependencies.

Screenshots and browser outputs are retained under
`.test-tmp/frontend-predictability/` (ignored generated artifacts). Sample zoom
screenshots were visually inspected; normal layout checks assert no document
horizontal overflow. The evidence table can scroll within its own container.

The mission console profile is `mission-console` version `1`, with SHA-256
`55df7b7b1ea4b48cbc6c0a70412bc01c3e8436a26a8c6968676d76c3df7314b9`.
Its two new `mission-console-v1-*.png` reference images were visually inspected
and passed a subsequent screenshot comparison. Historical reference images are
retained. Spanish mission layouts were also inspected. The keyboard test now
requires an actual button when looking for an aircraft: the new focusable tab
panel had exposed a false match against its descendant alert text.

All implementation tasks passed review, including scoped re-reviews of fixes.
The final independent review approved the combined implementation with no
actionable findings. Implementation and verification took place in the isolated
`codex/frontend-predictability` worktree.

`python3 -B scripts/verify_documentation.py` also passed. The original checkout's
pre-existing changes were left untouched.

## Practical limits

These are software and browser checks, not physical timing or human calibration.
No real station display identification, joystick/audio timing, Windows native
window placement, or human qualification was measured in this run. Native
visual-profile IDs/hashes, experimental geometry, engine logic, task shortcuts,
protocol order and scoring were preserved. Upgrade between active sessions.
Historical save details that were never recorded remain unknown.
