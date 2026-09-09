# Evidence branch consolidation: isolated software verification

The consolidation connects the complete evidence workflow to `main`: native
capture, reconciliation, immutable storage, Console inspection, frozen analysis
selections and offline-verifiable export. PRs #63 and #64 had been merged into
feature branches. Their closed status did not establish default-branch delivery.

## Revisions and actual execution

- Integration merge: `27ba2572b25c56335ece6a6ec34541695a40625d`.
- Verified correction: `953facf08ca30581e7a529e31533fd2eda16dadf`.
- The only source difference between these revisions is the POSIX fake-process
  termination path in `test_draft_visual_preview_is_isolated_and_abortable`.
  Without it, Linux's `killpg` cannot terminate the fake child and the test waits
  indefinitely. The application process-management implementation is unchanged.
- Both Python suites below ran on the corrected revision. Linux frontend and
  browser checks also ran there. Windows frontend checks ran on the identical
  frontend tree at the integration merge.

| Check | Windows | Linux |
|---|---:|---:|
| Repository contracts | 582 passed, 9 skipped | 582 passed, 9 skipped |
| Native OpenMATB | 848 passed | 848 passed |
| Full backend | 277 passed, 1 skipped | 277 passed, 1 skipped |
| Frontend unit tests | 147 passed | 147 passed |
| Lint, TypeScript, production build | Passed | Passed |
| Production evidence browser acceptance | 1 passed | 1 passed |

The browser scenario uploads a synthetic capture, selects metric source events
and linked timing, checks an exclusion, downloads its export, recomputes it
offline and reopens the stored capture. It is not a visual exposure or timing
qualification, nor the entire browser suite.

## Isolation and reproducibility

Windows used a new Git worktree, a new Python 3.12.13 virtual environment with
freshly installed requirements, a verified official Node 22.23.2 distribution,
and `npm ci`. It used the existing Windows 11 host, not a newly installed OS.
Linux used a fresh Debian bookworm container, Python 3.12.14, Node 22.23.2,
fresh Python/npm installations and Playwright's system dependencies. The image
digest was `sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254`.
Both environments ran on the same physical host. This is isolated software
verification, not an independent laboratory replication or target-rig approval.

Retained [results and commands](evidence-integration-2026-09-09/results.json),
[JUnit/browser/build results](evidence-integration-2026-09-09/test-results.zip),
[Windows dependencies](evidence-integration-2026-09-09/windows-python-environment.txt)
and [Linux dependencies](evidence-integration-2026-09-09/linux-python-environment.txt)
make the executed versions and outcomes inspectable. Hostnames and user paths
were redacted from the shared logs; test outcomes were not edited.

From a fresh checkout, install Python 3.12 and the OS-specific retained versions
as constraints on `requirements-dev.txt`, `openmatb/requirements-dev.txt` and
`openmatb/requirements.txt`. Install Node 22.23.2. Then run:

```text
python scripts/verify_evidence_release.py . <results-directory> --frontend
```

The runner retains reports even after failed checks and exits unsuccessfully if
any requested step fails. Pytest uses native system temporary storage outside
Git. A Git archive is insufficient for tests that verify the tracked public-core
inventory; a Windows bind mount is unsuitable for Linux's unlinked temporary
capture files. Initial setup failures remain retained locally and are not counted
as application test passes.

## Hosted CI and remaining release boundaries

GitHub Actions run `34389458176` has six failed jobs with zero executed steps and
no assigned runners. Its check annotation explicitly reports failed recent
payments or a spending limit. The account owner must resolve **Billing & plans**
and rerun hosted verification. No workflow gates, test assertions, branch
protection settings or scientific release criteria were relaxed here.

Recorder overhead, physical onset, target-rig timing, human calibration,
physiological synchronization and cross-implementation characterization remain
separate evidence classes. This consolidation is not a qualified scientific
release and does not promote legacy CSV or provisional metrics.
