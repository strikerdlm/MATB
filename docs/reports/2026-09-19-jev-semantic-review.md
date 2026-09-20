# JEV semantic-review implementation verification

Source baseline: `2d57ef132be3813ec039b3f028920b5abd1be1e9`.
Branch: `codex/feat-jev-semantic-review`. Platform observed: Windows, Python 3.12
in the existing `matb` Conda environment, Node 24.18.0. No Linux execution,
authenticated provider call, physical timing test or human validation is claimed.

## Observed software checks

- Baseline automation/component tests: 46 passed.
- Latest targeted inference Python/backend tests: 82 passed, including synthetic
  annotation → station projection → single mocked provider attempt → export and
  replay with unchanged evidence rows.
- Full root suite: 902 passed, 7 skipped, 6 Git-inventory failures. The public-core
  file rerun with process-scoped `safe.directory` passed all 11 tests, including
  those six failures. No global Git trust configuration was changed.
- Full backend suite: 489 passed, 1 skipped, 9 setup failures. All nine passed on
  rerun after preparing repository-pinned FastAPI 0.116.2 / Starlette 0.48.0 and
  exact offline replay wheels in worktree-local test directories.
- Full frontend Vitest suite: 282 passed across 84 files. Later targeted
  StrictMode and export regression tests: 4 passed.
- Frontend typecheck, lint and production build passed. An initial build using a
  shared dependency junction was rejected by Turbopack; a worktree-local offline
  `npm ci` resolved that environment limitation.
- Original `npm run test:e2e:core` did not start: ports 8000/3100 were occupied.
  Existing services were not stopped. The dedicated mocked semantic browser test
  passed (1 test), including exact preview, complete blinded labels, disclosure,
  narrow-layout overflow and Axe WCAG 2 A/AA checks. It used isolated ports
  3331/8331 and no provider. An initial contrast failure was fixed and rechecked.

Commands used the repository's tests, without weakening existing assertions.
`PYTHONNOUSERSITE=1` avoided an unrelated user-site LangSmith pytest plugin.
Backend rechecks used worktree-local pinned packages on `PYTHONPATH` and
`MATB_DESCRIPTIVE_WHEELHOUSE`; shared environments were not modified.

## Independent review

Read-only independent review identified and drove regression fixes for default
header mutability, nested mappings, JSON validity, canonical identity, blinding,
replicate/export exposure, retry timing, queued cancellation, unknown transport
outcomes, late replay disposition, StrictMode and unsupported configuration.
The review is software assessment only and does not replace institutional gates.

## Remaining qualification gates

Participant egress is hard blocked. Data-custodian review, API-specific retention
and upstream processing clarification, protocol authorization and empirical human
evaluation remain outstanding. The feature does not include physiology, future
prediction, shadow recommendations or live adaptive control. No unrelated roadmap
qualification checkbox has been marked complete.

## Final commands and scope

Targeted Python checks: `python -m pytest tests/inference` plus the five
`webui/backend/tests/test_inference_{api,sources,station,component,export}.py`
files: 82 passed. The API file was rerun after adding a positive complete-label
case: 4 passed. Frontend: `npm run typecheck`, `npm run lint`, `npm run build`,
and `npx playwright test --config=playwright.semantic.config.ts` passed. The
browser run used a fresh output directory to avoid mixed-user Windows output ACLs.

Independent review's final encoding finding was corrected; the subsequent
production build and bilingual browser selectors passed. Empty reference labels
were observed failing the new rejection assertion before implementing strict
ontology coverage. The UI now requires all three categorical labels.

This is a synthetic-only software implementation. The planned participant-enabled
release and empirical benchmark remain gated; the benchmark report records no
accuracy estimate. Standard core end-to-end coverage remains unexecuted in this
workspace because its ports were occupied. No merge or remote publication occurred.
