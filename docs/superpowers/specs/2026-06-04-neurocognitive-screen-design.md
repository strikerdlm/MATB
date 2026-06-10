# Baseline Neurocognitive Screen (Phase 10 #20) — design

Date: 2026-06-04
Status: approved by Diego (design + Spanish-presentation amendment)
Role: per-participant HCF source for the Suhir DEPDF fits (closes the F = F₀
assumption). Roadmap item: phase8_feature_spec.md #20 ("RT, WM, tracking
baseline"); evidence review §5.8 (CogScreen-AE / ANAM-aligned).

## 1. Scope decisions (locked)

- **Role:** HCF source only. Administered **once at enrollment**, before
  visit 1. Per-session re-administration is out of scope.
- **Platform:** browser, inside the console webui (`/screen` page),
  `performance.now()` timing. No new runtime.
- **Architecture:** raw-trials-to-backend. The browser captures raw trial data
  and POSTs it; a versioned Python scorer in `matb_integration/screen/`
  computes all scores and the HCF mapping. No metric math in TS; raw trials
  persist so scoring is re-derivable.
- **Language:** ALL participant-facing content (instructions, practice
  prompts, countdowns, completion message) is **es-CO Spanish**, centralized
  in `webui/frontend/src/components/screen/strings_es.ts` for single-point
  review. Researcher-facing UI (picker, scores, console chrome) stays English.
  Task instructions are operational text, not a psychometric scale — no formal
  validation requirement, but the wording follows the register of the
  validated `nasatlx_es` assets.

## 2. Battery (4 subtests, ~10–12 min, researcher-administered)

| # | Subtest | Trials | Stimulus/response | Score | z-sign |
|---|---|---|---|---|---|
| 1 | Simple RT | 30 | Visual target, random ISI 1–3 s; spacebar | median RT (ms); trials < 150 ms discarded as anticipations | − |
| 2 | Choice RT | 30 | 2-choice left/right; ←/→ keys | median **correct** RT (ms); accuracy recorded | − |
| 3 | 2-back (letters) | 60 (~20 targets) | Consonants only (B C D F G H J K L M), 2.5 s SOA; spacebar on match | d′ via the **same Hautus log-linear helper as SYSMON** (`matb_integration.log_converter` probit/d′ — reused, never re-implemented) | + |
| 4 | Pursuit tracking | 90 s | Mouse follows a sum-of-sines target path (OpenMATB-style) | RMS error, normalized to target-path amplitude | − |

Each subtest: Spanish instruction screen → 5 practice trials (excluded from
scoring) → scored block. Order fixed (1→4). Fullscreen task runner with
progress indicator.

## 3. HCF mapping (pre-specified; exploratory-labeled everywhere)

- Per-subtest **cohort z-scores** (computed over all participants with a
  stored screen), sign-aligned per the table above.
- Composite z̄ = mean over **valid** subtests.
- **F/F₀ = 1 + k·z̄ with k = 0.05, clamped to [0.85, 1.15].**
- **Pre-registered gates:**
  - HCF computed only when **≥ 3 participants** have screens; below that all
    fits stay F = F₀ with `hcf_source = "F0_default"`.
  - Subtest validity: ≥ 80% usable trials; Choice RT additionally requires
    accuracy ≥ 60%. Invalid subtests are excluded from the composite and
    recorded as such. "Usable" per subtest: Simple RT — responded, RT ≥ 150 ms;
    Choice RT — responded within the response window; 2-back — stimulus shown
    full SOA (all normally are; guards against tab-switch gaps detected via
    timestamp drift > 250 ms); tracking — ≥ 80% of expected mouse samples
    captured (the whole subtest is the "trial").
- Mapping constants live in one versioned module
  (`matb_integration/screen/hcf_mapping.py`, `SCREEN_VERSION`); every fit and
  artifact records the screen version, formula, and cohort-n used.
- The mapping has no validated external standard (Suhir §5.9's FOM approach is
  itself heuristic) — every surface that shows a screen-derived F labels it
  **exploratory**.

## 4. Where F enters the model

Calibration (Eqs. 5.19–5.21) is MWL-side and F-independent — **g0/p0/τ0 never
change**. F enters at evaluation: with a screen-derived HCF the participant's
P^h curve switches from Eq. 5.16 (ordinary capacity) to full Eq. 5.1
(`p_bar(g², f²)`, already Table-5.1-validated). Because cohort z-scores shift
when a new participant is screened, **every screen ingest refreshes
`hcf_value`/`hcf_source` on ALL existing DepdfFit rows** (no re-calibration —
only the HCF columns) and `/fits` curves recompute server-side with the
participant's F.

## 5. Data model + endpoints

- `ScreenResult` table: `participant_id` (FK, **unique** — one baseline per
  participant), `administered_at`, `screen_version`, `raw_trials_json`,
  `scores_json`, `created_at`.
- HCF itself is **derived, never stored per-screen** (cohort-relative, same
  principle as the completeness grid); `DepdfFit.hcf_value` snapshots it at
  fit/refresh time.
- Endpoints:
  - `POST /screen` — raw payload → validate → score (Python) → store →
    refresh all DepdfFit HCF columns. Rejects a second screen for the same
    participant unless `overwrite=true`.
  - `GET /screen` — per-participant scores, current cohort F values, gate
    status (n screened vs the ≥ 3 gate).
  - `GET /fits` — gains the F-aware curve (Eq. 5.1 when
    `hcf_source = "screen"`).

## 6. Frontend

`/screen` page: participant picker (unscreened participants only) → fullscreen
Spanish task runner → completion screen → POST → researcher-facing score
summary rendered from the backend response (the browser displays nothing it
computed itself). Tracker gains a per-participant "screened" indicator.
Sidebar gains the Screen item.

## 7. Testing

- Python scoring oracles: synthetic trial sets with known medians/d′/RMS
  (d′ cross-checked against the existing SYSMON helper's published-value
  tests).
- HCF mapping units: known z → F, clamping at both bounds, n < 3 gate,
  invalid-subtest exclusion, sign alignment.
- Backend: ingest → score → fit-refresh propagation (a second participant's
  screen must change the first participant's `hcf_value`); duplicate-screen
  guard; gate statuses.
- Frontend vitest: trial sequencing, payload shape, validity flags
  (timing-independent logic only).
- Live e2e: Playwright-driven keypress trials through the full battery,
  ingest, fit refresh on the cohort DB, curve change verification.

## 8. Out of scope (YAGNI)

Per-session re-administration; norm-referenced scoring; divided-attention
subtest; joystick tracking; participant self-service; English participant
strings.
