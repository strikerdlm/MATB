# Task 7 — whole-study restoration and release verification

Implementation owner: `/root/study_restore`; delegated by `/root`. Worktree
`/root/repos/MATB/.worktrees/repeatable-study`, branch `codex/repeatable-study`.
Base: `5619495c85ba5940f0655aa5cae35f3914f0b59c`.

The user's instruction, “no re-review. Just make it sure it works and tests pass
now”, was applied: no reviewer or review loop was launched. Parent owns pushes,
PR and actual both-OS CI monitoring. No merge/deployment/publication is authorized
by this report. Existing scientific and release qualification blockers remain.

## Completed implementation

- Added stdlib whole-study backup/restore/reproduction in
  `webui/backend/app/study_backup.py` and standalone `tools/study_workspace.py`.
  Backup takes `BEGIN IMMEDIATE` before checking exclusive maintenance and holds
  it through the DB snapshot, artifact inventory, hashes and archive activation.
  Live reservation/lanes/running or uncertain writers fail closed. A concurrent
  writer test proves the lock covers artifact inventory.
- Preserve the complete SQLite database, immutable evidence/qualification blobs,
  all HCF/analysis tables, frozen source/wheel kits, exact preparation admission
  frontiers, raw native/Polar/Liftoff/mission artifacts and station job responses.
  Inventory the five configurable artifact roots plus persisted record paths,
  scenario paths and response artifacts. Validate recorded native sidecar,
  physiology and mission/Liftoff checksums. Missing required sources fail;
  incomplete source states remain explicit. No scientific bytes are rewritten.
- Restore verifies safe portable archive paths, exact inventory/checksums,
  SQLite integrity/FKs, bound study/version/plan fingerprints, preparation
  presentation/configuration identities and accepted event frontiers, HCF and
  analysis fingerprints. Extraction is staged into an empty workspace and then
  activated by directory rename. Every SQLite handle is explicitly closed before
  Windows-sensitive replacement/cleanup. Missing optional implementation is an
  explicit capability failure, not permission to discard source files.
- Added explicit logical relocation through `artifact_paths.resolve_artifact` to
  native, physiology, Liftoff and simulation readers. Original absolute paths in
  immutable manifests remain original; restored readers fail when no relocation
  mapping exists rather than falling back to the old external source. Preserve
  original-manifest.json, relocation.json and the restoration report.
- Regenerate operational authority only in the copied/restored DB. Retire the
  live backend instance lease, independent per-record controller/participant
  authority, station reservations/lanes and nonterminal jobs; strip queued HTTP
  controller headers. Mark previously started attempts interrupted/unknown;
  disable restored evidence/Bayesian automatic queue continuation. A regenerated
  local `.station-secret` is read through MATB_API_TOKEN_FILE. Maintenance remains
  active. Restored runtime identities require explicit new acquisition attempts;
  checkpoint recovery cannot resume restored acquisition.
- POST /station/backups records a named maintenance request and downloads the
  verified bundle. Bilingual Study → Restore and Station links provide keyboard
  access and explain offline empty-workspace activation. The CLI provides the
  matching backup, restore and reproduce operations.
- Offline reproduction extracts every frozen descriptive execution into a fresh
  output, creates a new venv without system-site packages, removes inherited
  Python/test paths and PIP settings, installs pinned included wheels with
  isolated pip `--no-index`, and runs packaged source under Python `-I` with
  outbound Python sockets denied. It checks actual import location, package
  versions, exact raw calculations/aggregation/fingerprints and figure bytes.
  Logs and source/figures remain; successful disposable venvs are removed.
  This is Python socket denial, not a claim of an OS network sandbox.
- Fixed native offline provenance: the selected native derivation's validated
  execution declaration is frozen in raw analysis inputs. The calculator checks
  actual source hashes and dependency versions before reconciling with that
  declaration. Original Git/OS metadata do not become accidental fresh lookups.
  Structured results are normalized through JSON before exact comparison,
  preserving tuple/list serialization semantics without a numeric tolerance.
- The whole synthetic journey exercises authored/frozen preparation, actual held
  native controller admission and the same synthetic process identity, H10
  simulated transport recording/markers, PVT baseline/interruption/repeat/post/
  recovery, native questionnaire/evidence, exact analysis selection, later
  classification and future-only amendment. Original owned fixture roots are
  renamed unavailable before restoration and fresh offline recomputation.
  The deliberately short H10 window stays invalid; no hardware/qualification
  claims or scoring/stimulus changes were introduced.
- Fixed a real native admission boundary exposed by this journey: creating the
  native source and obtaining held preflight no longer require an already-started
  shared attempt. Actual start still passes preparation/controller admission;
  no seeded-start or generic-runtime bypass was introduced.
- Added root restore/replay/wheel/station-load tools to the core allowlist. The
  physically stripped core test starts the actual application repeatedly,
  migrates/retains historical native evidence associations and blobs, backs up,
  restores to a new DB and starts again with optional product packages absent.
- Documented the complete workflow, commands, environment activation, provenance,
  offline limits and remaining scientific requirements in English and Spanish:
  docs/research/repeatable-study-restoration.md, linked from both READMEs.

## Clean-test fixes and coverage

FastAPI 0.116.2 / Starlette 0.48.0 use the current multipart package entrypoint;
no warning filter was added. SQLModel tests use select/Session.exec instead of
legacy Session.query. The normal Liftoff mixed-model fixture now has deterministic
participant and residual variation instead of three perfectly linear subjects;
existing cache/status assertions and separate degenerate model tests remain.

Parent's retained diagnostics identified a PyMC tau0 overflow in quadpotential.py
under ordinary warnings. Warnings-as-errors had masked that specific outcome via
the existing guarded error result, so that was not accepted as a clean result.
Bayesian version 2.2.1 changes numerical initialization only: observed-mean
intercept initval and adapt_diag avoid remote jittered initial positions. Priors,
likelihoods, known-effect assertions and convergence thresholds remain intact.
Tests now require all Q4 outputs to be successful and check the recorded
initialization. The original narrow simulation fixtures were retained.

The old nine scientific skips were audited concretely: five absent local CSV
checks now run on an explicitly synthetic legacy CSV; three obsolete DISPLAY/
absolute native checkout gates now exercise the bundled Sysmon constructor in an
isolated native test harness. Native ReplayScheduler/LogReader frozen-time behavior
has synthetic coverage. One explicit skip remains for the SAGAT runtime plugin
that is not shipped; generation/probe tests do not pretend that plugin exists.

Parent's bounded live traffic diagnostics found SwiftShader/software-renderer
input starvation: normal click 3211 ms, CPU4x 4565 ms, long tasks up to 1089/1206 ms,
without a navigation or infinite resize loop. Diagnostic traces/metrics are in
/tmp/matb-task7-traffic-diagnostic. Presentation tests now exercise actual traffic
selection before costly screenshots, retain real click/actionability and add
aria-pressed assertions; active 3D camera screenshots use the current viewport
instead of resizing the full page. Experimental geometry is unchanged. No force
click, noWaitAfter, retry increase, weakened selection or skipped assertion was
used.

Strict lint uses --max-warnings=0. Every required browser CI invocation uses
--fail-on-flaky-tests. The explicit both-OS study matcher now includes study-analysis,
station and study-restore. Actual 200% browser zoom runs on Linux through Xvfb/XTest
shortcuts (not CSS zoom), including study, analysis, station and restore surfaces
in EN/ES; Windows exclusion is explicit because this harness uses Linux XTest.

## Retained development evidence and resolved failures

Evidence directory: `.test-tmp/repeatable-study/task7`. All cited prior Task1–6
proofs and original checkouts were left intact. Each pytest run used a unique
basetemp; public-core exports used outside-repository /tmp roots.

- red.log: missing restore module contract failures before implementation.
- green-1.log: initial three restore tests passed with the pre-upgrade multipart
  warning; later clean runs supersede that warning, not its evidence.
- iteration-2.log: an import-insertion indentation error, corrected before the
  26-test iteration-3.log pass with no warnings.
- old-fixtures-1.log: one wrong assertion field in the replacement communication
  fixture; corrected to the existing SDT contract. core-fixtures-2.log then
  passed 146 tests with only the truthful missing-SAGAT-plugin skip.
- bayes-fixture-1.log retained a warning from the abandoned wider-fixture attempt;
  the original fixture was restored. bayes-initialization-1.log passed 14 tests
  without warnings after the numerical initialization fix.
- journey-1 through journey-3 exposed the required native questionnaire target,
  actual create/preflight admission ordering, and exact native H10 association;
  these were corrected without bypassing preparation/start contracts.
- journey-4 exposed an invalid function replacement of socket.socket that broke
  SSL/PyArrow class inheritance; replaced with an OfflineSocket subclass.
- journey-5/6 exposed the native execution-provenance fingerprint mismatch in an
  isolated environment. Full numeric/metric payloads matched; preserving and
  independently validating the frozen execution declaration repaired the real
  provenance issue. Failed source/log/figure evidence remains. Only disposable
  failed venv directories owned by these iterations were removed to conserve
  disk; successful proof artifacts and all raw data remain.
- journey-7.log: 15 passed / 47.33 s / zero warnings. Actual cross-instrument
  execution 6bf19eb0-e45f-49b1-a7ab-f8cb0a325e88 reproduced 5 raw attempts, exact
  figure SHA256 3d109d77a2df987fc787d4f932829614f420f6eacd5e4806d7a60ff3f1785044,
  42 restored files, Python isolation=1 and no system-site packages.

## Final verification

Final source inventory before the broad gates:
`.test-tmp/repeatable-study/task7/final-source-inventory-1.json` (43 changed/new
source and documentation files; generated tracked .pyc files excluded). No
production mutations occurred while those final gates were running.

All Python commands use `/root/repos/MATB/.venv/bin/python`,
PYTHONDONTWRITEBYTECODE=1 and isolated test dependency directories, without
modifying the shared installation. Task7's isolated web dependencies are in
/tmp/matb-task7-webdeps; base test dependencies are
/tmp/matb-predictability-testdeps; the optional transport prefix is
/tmp/matb-task6-transport-testdeps. The existing pinned descriptive wheel kit is
.test-tmp/repeatable-study/descriptive-wheels.

- Native (parent): 854 passed / 3.12 s / zero warnings. final-native.log/xml;
  /tmp/matb-task7-final-native-evidence-1. Command from openmatb:
  `python -B -m pytest tests -q -p no:cacheprovider --basetemp=... --junitxml=...`,
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 and the base dependency prefix.
- Scientific contracts (parent): 598 passed / 1 explicit missing-SAGAT skip /
  149.36 s / zero warnings. final-contracts.log/xml;
  /tmp/matb-task7-final-contracts-evidence-1. Command:
  `python -B -m pytest tests -q -p no:cacheprovider --ignore=tests/suas --ignore=tests/liftoff --ignore=tests/documentation --basetemp=... --junitxml=...`,
  with all three dependency prefixes above.
- Frontend: `npm test`, 271 tests / 81 files passed / 199.65 s;
  final-frontend-units-1.log.
- `npm run lint` with --max-warnings=0, `npm run typecheck`, and
  `NEXT_TELEMETRY_DISABLED=1 npm run build` passed;
  final-lint-1.log, final-types-1.log, final-build-1.log.
- Documentation verifier passed (final-docs-1.log and parent's final-docs.log).
  Parent's candidate core dry run passed; the ordinary dry run needs the new
  root tool tracked at commit, as expected for an untracked implementation file.

Final backend/browser results and the commit integration handoff follow below.
Actual Windows CI remains the parent's post-push gate, never inferred from Linux
local success.

### Final verification corrections (actual test failures, not review loops)

The first concurrent auto/core backend runs exhausted the available disk while
retaining all previous proof trees. `final-backend-auto-1.log` records 483 cases,
481 completed passes, one opposite-OS skip, and the last whole-journey failure;
JUnit writing itself then failed with ENOSPC, so its XML is truncated and no
complete warning summary exists for that run. The failed whole-journey directory
is retained at /tmp/matb-task7-final-backend-auto-1. This run is not reported as a
clean full-suite pass.

Parent's `final-backend-core.log/xml` reports 348 passed, 36 skipped, one failed
lease-backup case and two setup errors (native calculator and isolated calculator
wheel case); all three failures were confirmed disk/setup-directory failures.
Two actual new Starlette warnings were also exposed in the oversized-ingest
paths. `HTTP_413_REQUEST_ENTITY_TOO_LARGE` was replaced with the current
`HTTP_413_CONTENT_TOO_LARGE`, preserving status 413. Parent's exact five-case
correction passed 5 / 32.27 s / zero warnings in
`final-backend-core-envfix.log/xml`, with unique basetemp
/tmp/matb-task7-final-core-backend-envfix-1. This covers all three interrupted core
cases and both upload-cap paths; it is not described as a second full run.

To restore capacity, only completed disposable venvs were removed after preserving
pyvenv.cfg and installed-package inventories. All original raw sources, wheel
kits, source snapshots, checksums, figures, logs and proof directories remain.
The two auto-run old-calculator environment inventories sit beside their former
venv paths. Parent similarly inventoried/removes its completed core environment
and four completed environments from prior Task5/Task6 proof trees; the parent
records those exact paths separately. No participant data or user artifacts were
deleted. Heavy offline jobs were then completed before browser verification.

The first browser run, `final-browsers-study-1.log`, completed 37 passes and three
failures: the Spanish 1920×1080 setup helper fired while the participant selector
was still disabled, and both new restore cases exposed a configured instrument
output directory that had never been used/created. The selector helper now stays
disabled while its controls cannot accept focus, including a deterministic
pending-participant regression; no artificial browser test wait hides the race.
Unused configured output roots are preserved as empty relocated directories;
paths referenced by persisted source records remain required and fail if missing.
Both boundaries have explicit tests. The restore browser test now asserts the
actual backup HTTP result promptly before waiting for the download, preserving
an actionable error instead of masking it in timeout cleanup. The first browser
server also recorded ENOSPC during shutdown; that isolated fixture DB and failure
artifacts remain retained. No failed outcome was accepted as a release pass.

The corrected final source inventory is `final-source-inventory-2.json`: 46
changed/new source/docs files. Source hash comparison after starting the final
browser pipeline showed no drift. Lint, types and production build passed again
in final-lint-2.log, final-types-2.log and final-build-2.log. The updated setup unit
suite passed 5 / 2.73 s (the original four plus the delayed-loading regression),
bringing distinct frontend unit coverage to 272 across the broad and corrected
runs. The color environment wrapper also preserves NO_COLOR intent through
FORCE_COLOR=0 without passing conflicting Node environment variables to workers.

`final-restoration-2.log/xml` passed all 19 restoration contracts / 78.84 s / zero
warnings at /tmp/matb-task7-final-restoration-2. This reran the entire whole-study
journey, real PVT-only offline replay, archive/semantic/path safeguards, lease
retirement, writer exclusion and new unused-root boundary on the corrected source.
The final cross-instrument execution is 7759c27c-06df-40e5-8d80-9f36f39101fc,
with 5 recomputed raw attempts and the same exact figure SHA256
3d109d77a2df987fc787d4f932829614f420f6eacd5e4806d7a60ff3f1785044.
The final PVT-only execution is bbd9e8d7-91fa-4018-abf1-937135ca3803.
Both offline-report.json files record isolation=1, system_site_packages=false,
actual packaged calculator import paths and socket denial. Original fixture
workspaces were unavailable throughout restoration/reproduction.

Across the broad backend runs and their bounded corrections, all 483 distinct
full-component cases and 351 distinct core cases have passed; the full run has
one explicit opposite-OS native process exclusion, and core has 36 exclusions
(the prior optional/OS inventory plus the native/H10 whole-journey test). The additional unused-root case passed in the full-component restoration subset;
it is also selected by the core CI gate, whose expected final count is 352. These
are combined distinct-case totals, not invented single-run results. Fresh full
Linux/Windows CI remains required after the parent's push.

### Final browser and packaging gates — complete

The required browser pipeline ran sequentially with MATB_COMPONENTS=auto,
MATB_PYTHON=/root/repos/MATB/.venv/bin/python, the isolated Task7 web/base Python
prefixes, unique final-browsers-* output directories, and
`npm run test:e2e -- --fail-on-flaky-tests --output=...` (test:e2e:core for core).
There were no retries or accepted flaky outcomes:

| Gate / retained log | Actual result |
| --- | --- |
| final-browsers-study-2.log | 40 passed / 2.9 min |
| final-browsers-geography-1.log | 14 passed / 1 explicit online opt-in skip / 2.6 min |
| final-browsers-evidence-1.log | 1 passed / 7.7 s |
| final-browsers-core-1.log | 2 passed / 6.0 s |
| final-browsers-zoom-1.log | 2 passed / 28.1 s |

Total: 59 browser passes. Geography enabled MATB_E2E_TRAFFIC_FIXTURE=1 and
MATB_E2E_REGION_CHECK=1. Matchers exactly selected the required study group,
geography/geography-assets/presentation, evidence, core designer and browser-zoom
specs. The three active 3D LOW/MEDIUM/HIGH control cases passed in 20.5/20.6/22.2 s,
including actual FIXTURE01 click and aria-pressed selection. Bilingual restore
cases downloaded the real verified ZIP and invoked the local restore CLI into
separate empty non-ASCII directories, then checked the actual restoration report.
The final run's server shutdowns completed normally.

The physical-core fixture was strengthened once more to exercise the actual
legacy evidence schema: after ingesting owned synthetic native evidence, it
removes the formerly absent parent column/index, then the real app lifespan
migrates the old schema and preserves unknown historical parentage, association
identity and all immutable source bytes through backup/restore/startup.
`final-core-legacy-2.log/xml` passed 1 / 6.62 s at
/tmp/matb-task7-final-core-legacy-2. Only that root test fixture changed after
inventory 2; no production, scientific calculator or browser source changed.
`final-source-inventory-3.json` records that test-only delta and the final 46
source/docs file hashes. The full contracts' 598 distinct passing cases remain
covered, with the changed physical-core case explicitly rerun.

## Commit and parent integration handoff

Staged only the 46 files in final-source-inventory-3.json and this force-added
report. Restored only the ten generated tracked aircraft_monitor .pyc changes;
these are execution byproducts, not implementation. No raw/test evidence or
unrelated checkout files are included in the source commit. No push, PR update,
merge or deployment is performed by the implementation owner.

Parent should verify committed file hashes against inventory 3, run the ordinary
core dry run now that the new CLI is tracked, push the branch, and inspect fresh
actual CI on Ubuntu/Windows. Expected current case counts are 598 contracts +
1 missing-native-SAGAT-plugin exclusion; 854 native tests; 483 full-backend +
1 opposite-OS exclusion; 352 core-backend + 36 intentional optional/OS exclusions;
272 frontend unit tests; browser selections 2 core + 14 geography + 1 evidence +
40 study, plus 2 actual-zoom cases on Linux. The geography online opt-in exclusion
remains explicit. CI browser retries, if any, must fail the new flaky gate and be
repaired; checkpoint Task6 green status is not a substitute for this final run.

This completes the bounded P0+P1 implementation and local distinct-case
verification. Physical timing/H10 hardware, human calibration and reliability,
SAGAT plugin availability, public reference data, privacy/licensing requirements,
and the deferred P2 station inventory/synchronization/replay/shared-network
capabilities remain truthful limitations. No scientific qualification was promoted.

### CI-only Node 24 action correction

Workflow 34550487523 at 5435e38 emitted actual Node 20 action-runtime deprecation
annotations. Updated the 10 existing checkout/setup-python/upload-artifact/
setup-node references to immutable official release commits, verified directly
against GitHub release tag objects and the action.yml at each commit:

| Official action | Release | Immutable commit / verified metadata |
| --- | --- | --- |
| actions/checkout | v7.0.1 | [3d3c42e5aac5ba805825da76410c181273ba90b1](https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/action.yml) |
| actions/setup-python | v7.0.0 | [5fda3b95a4ea91299a34e894583c3862153e4b97](https://github.com/actions/setup-python/blob/5fda3b95a4ea91299a34e894583c3862153e4b97/action.yml) |
| actions/upload-artifact | v7.0.1 | [043fb46d1a93c77aae656e7c1c64a875d1fc6a0a](https://github.com/actions/upload-artifact/blob/043fb46d1a93c77aae656e7c1c64a875d1fc6a0a/action.yml) |
| actions/setup-node | v7.0.0 | [820762786026740c76f36085b0efc47a31fe5020](https://github.com/actions/setup-node/blob/820762786026740c76f36085b0efc47a31fe5020/action.yml) |

All four declare runs.using=node24. The previous setup-node commit 49933ea also
explicitly declared node20. YAML parsing/structural comparison passed: only the
action references changed; every configured action input remains supported and
job commands, matrix, permissions and application Node/Python versions are
unchanged. Retained official metadata and validation are in
`task7/actions-node24-official-metadata.json` and `actions-node24-validation.json`;
`final-source-inventory-4.json` records only the workflow hash delta from inventory
3. No production changes or local scientific/browser suite reruns. Parent owns
push and the fresh full GitHub verification; no re-review was performed.

### Windows JSONL reader correction — test only

Actual Windows contracts job 103113281099 in workflow 34550840968 failed the
newly unskipped CSV/JSONL round trip (597 passed, 1 failed, 1 skipped). Diagnosis:
`convert_to_jsonl` already writes UTF-8 explicitly with ensure_ascii=False;
the test used Path.read_text() without an encoding, so the Windows locale decoder
changed the non-ASCII csv_path. Production serialization/scoring is unchanged.

The reader now explicitly uses UTF-8. The same complete-object equality remains,
with additional owned `captura ñ/航空.csv` source path and `carga_baja_ñ` metadata
assertions and exact UTF-8 line-byte verification. Parameterized wrappers simulate
both UTF-8 and cp1252 default text opens, including Path's `locale` sentinel, on
producer and reader while preserving explicit encodings and binary reads. This
exposes the Windows boundary on Linux without global UTF-8 environment coercion.

`jsonl-encoding-red-2.log`: the cp1252 case reproduced the exact path/data corruption
(1 failed, 1 passed). After the explicit reader fix, the complete focused converter
suite passed 67 / 0.26 s / zero warnings: `jsonl-encoding-final-1.log/xml`, unique
basetemp /tmp/matb-task7-jsonl-encoding-final-1. Command:
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/matb-predictability-testdeps /root/repos/MATB/.venv/bin/python -B -m pytest tests/test_log_converter.py -q -p no:cacheprovider --basetemp=... --junitxml=...`.
No broad suites/re-review or production mutation. Inventory 5 records only the
converter test hash delta from inventory 4; the expected contracts pass count is
now 599 plus the explicit missing-SAGAT-plugin skip. Parent holds the push while
remaining current CI jobs finish, so any additional actual failures can be batched.
