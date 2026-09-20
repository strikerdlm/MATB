# JEV v1 software completion verification — 20 September 2026

Baseline: `782a7d3` (merged PR #72). Follow-up branch:
`codex/feat-jev-review-completion`.

## Delivered

Capture-scoped paginated annotation/run retrieval; immutable note-version reuse
and linked edits; restored frozen previews; named history-exposure auditing;
append-only revocation serialized with dispatch; explicit fresh-approval retries;
bilingual answer/distribution/confidence and diagnostic displays; disagreement
history; optional self-started coding timer; schema 1.1 provenance exports with
original note chain, exact approval JSON/hash and cross-attempt audit history;
backward-compatible network-free replay; a frozen lexical comparator and offline
language-stratified evaluation with paired participant-cluster bootstrap intervals.

No changes to evidence metric calculation, acquisition, scientific eligibility,
automation evaluation/application, or participant-egress restrictions.

## Observed checks

| Check | Result |
|---|---|
| Windows `python -m pytest tests -q` | 933 passed, 7 skipped; 804.47 s |
| Windows `python -m pytest webui/backend/tests -q` | 500 passed, 1 skipped; 967.17 s |
| Final focused inference + five backend inference files | 98 passed; 14.43 s |
| Frontend `npm run test` | 287 passed across 84 files |
| Frontend typecheck / lint / production build | Passed |
| Mock semantic browser + Axe WCAG A/AA | 1 passed; preview, timer, labels, distribution, history, mobile and reload |
| Core experiment-designer E2E | 2 passed on isolated ports 8332/3332 and a temporary database |
| Ubuntu Python 3.13 inference suite | 82 passed; 17.99 s; one cache-write permission warning |
| Offline baseline / benchmark CLI smoke | Passed on synthetic local fixtures; no remote calls |
| Branch whitespace check | Passed |

The standard core E2E launcher refused occupied ports 8000/3100. A temporary
configuration retained the same test file/assertions and changed only server
ports/origin, output path and isolated database. Existing services were preserved.

Windows used the existing Python 3.12 `matb` Conda environment and Node 24.18.0.
`PYTHONNOUSERSITE=1` excluded unrelated user-site pytest plugins. Backend checks
used worktree-local FastAPI 0.116.2 / Starlette 0.48.0, plus the existing pinned
offline replay wheelhouse. Root tests used process-scoped Git `safe.directory`.
Tracked bytecode modified by child test processes was restored before staging.

Ubuntu's system Python lacked pytest and ensurepip. No system package was changed:
Linux wheels were unpacked into a worktree-local target and used via `PYTHONPATH`.
Direct test pins: pytest 8.4.2, Pydantic 2.13.4 / pydantic-core 2.46.4, HTTPX 0.27.0.
Resolved support packages: annotated-types 0.8.0, anyio 4.15.1, certifi 2026.7.22,
colorama 0.4.6, h11 0.16.0, httpcore 1.0.9, idna 3.20, iniconfig 2.3.0,
packaging 26.3, pluggy 1.6.0, Pygments 2.21.0, sniffio 1.3.1,
typing-extensions 4.16.0, typing-inspection 0.4.4.
Linux ran `python3 -m pytest tests/inference -q` with plugin autoload disabled;
the cache warning did not affect assertions. Linux backend/UI suites were not run.

## Review and test-first evidence

The history endpoint initially returned 405; the integration test then passed
through note creation, projection, mock inference, hidden history, exposure,
export/replay, retry and revocation. UI retrieval initially failed on the missing
control. Evaluation tests initially failed on the missing module, then paired
comparison output. Timing metadata initially returned 422 before implementation.

Independent read-only review identified two material findings. Reviewer handoff
retained exposed reference labels; a failing UI regression now passes after
clearing exposure-bearing state and guarding pending replies. Common English
contractions and Spanish negation bypassed the conservative baseline; four failing
examples now pass after normalization. No minor findings were deferred.

## Decisions and remaining non-software gates

- Participant transmission stays hard blocked. Enabling it requires reviewed
  institutional data-processing/protocol arrangements and a separate code change.
- Named-rater audit is not identity authentication; institutional assignment and
  access controls remain necessary. Clearing a screen cannot erase human memory.
- Noul benchmarking concerns explicit textual presence, with absent/unmentioned
  source codes retained separately. It does not estimate physiological condition.
- No authenticated JEV request, human accuracy study, physical timing measurement,
  forecasting, physiology fusion, shadow policy or intervention was performed.
- Synthetic calculations establish software behavior only. No empirical accuracy,
  efficiency improvement, or evidence-based keep/remove decision is claimed.

Live provider compatibility and human validation remain unperformed. The relevant
protocols and executable offline analysis tooling are available for those studies.
