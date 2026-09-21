# Research Console production review — 2026-09-21

Scope: the local FastAPI/Next.js Research Console and synthetic sUAS console on
the current swarm branch. This review covers software deployment and regression
checks. The empirical qualification, licensing and public-release gates in the
root README still apply. It does not qualify an Internet-facing service, hardware
timing, clinical use or human-performance interpretations.

## Corrected issues

| Area | Defect and correction |
| --- | --- |
| Connection recovery | A rejected runtime-config request was cached indefinitely. Failed discovery now clears only its own cache entry so a later retry can reconnect; concurrent callers still share one request. |
| Deferred analysis | Malformed JSON and invalid analysis selections reached metadata capture before FastAPI validation and raised server errors. Admission now uses the endpoint's request schema before snapshotting or queueing, with a bounded, non-reflective 422 response. |
| Browser errors | Admission and size-limit errors bypassed CORS. Allowed browser origins can now read the actual error response. Host and mutation-origin checks remain in place. |
| Authentication errors | Non-ASCII bearer input could raise from `compare_digest`. Byte comparisons reject invalid credentials without a server error. |
| Shutdown ownership | A provider shutdown failure could release database ownership while native work remained alive; a station-worker failure skipped Bayesian cleanup. Failed shutdown now retains the lease until process exit and still attempts each cleanup path. |
| Deferred request cleanup | Background requests bypassed FastAPI's file-cleanup context. The station worker now supplies the request exit stack required by the patched framework. |
| Log confidentiality | Uvicorn WebSocket accept messages included query-string controller leases. Both access and error loggers now redact lease/token query values, preserving the structured arguments required by Uvicorn's access formatter. |
| Browser protection | Production responses now prohibit framing and MIME sniffing, suppress referrers and omit the framework identification header. |
| Accessibility | Mission setup nested a second `main` inside the application shell. Its content now uses the shell's single main landmark. |
| Verification | Managed browser checks now honor `MATB_NEXT_DIST_DIR`; a production acceptance command covers desktop/mobile compilation, page headers, readable validation errors, swarm controls, replay and SAGAT concealment. CI runs this command. |

## Dependency changes

The backend pins FastAPI 0.141.1, Starlette 1.6.0, AnyIO 4.14.2 and setuptools
83.0.0, with security floors for HTTPcore, h11, IDNA and Pygments. Existing
scientific calculation constraints remain unchanged. Validation used Python
3.12.13 and Node 24.18.0 on Windows; CI retains its separate Linux/Windows matrix.

The old Starlette pin was affected by the maintained advisories for
[Range-header denial of service](https://github.com/Kludex/starlette/security/advisories/GHSA-7f5h-v6xp-fcq8),
[Windows StaticFiles UNC-path handling](https://github.com/Kludex/starlette/security/advisories/GHSA-wqp7-x3pw-xc5r),
and [form parsing limits](https://github.com/Kludex/starlette/security/advisories/GHSA-82w8-qh3p-5jfq).
Applicability depends on the endpoint; updating the framework avoids carrying
these affected versions into a fresh deployment. Other dependency floors follow
the fixes reported by pip-audit for the installed project dependency graph.

The final audit of all 86 resolved project dependencies reported no known Python
vulnerabilities. `npm audit` reported zero frontend vulnerabilities. These are
point-in-time dependency checks, not proof that the application is vulnerability-free.

## Deployment and verification

Use a dedicated Python environment and install the updated repository
requirements. An older workstation environment can import FastAPI successfully
while still missing the HTTP status symbols and lifecycle behavior required by
this application. Do not treat import-only checks as version verification.

The exact audited Windows/Python 3.12 package closure is retained in
[`release/requirements-windows-py312.lock`](../../release/requirements-windows-py312.lock).
This platform-specific lock includes the verification dependencies; Linux
installation continues to use the repository requirements and its own CI matrix.

Follow the existing [release runbook](suas-swarm-release.md) for persistent data,
backup, process ownership, loopback binding, startup and rollback. Preserve the
matching code, environment and dependency identities for archived studies.
Prepare calculator wheels with the same interpreter that runs the backend:

```powershell
python -m pip install -r release/requirements-windows-py312.lock
python tools/prepare_study_wheels.py .test-tmp/production-wheels
$env:MATB_DESCRIPTIVE_WHEELHOUSE = "$PWD/.test-tmp/production-wheels"
```

The wheel preparation step downloads software packages only. Analysis and export
subsequently use those pinned local files. Keep the directory available to the
backend; a missing wheel correctly prevents an allegedly portable export.

From `webui/frontend`, with `MATB_PYTHON` pointing to that interpreter:

```powershell
npm ci
npm run build
npm run test:e2e:production -- --fail-on-flaky-tests
```

The production browser suite owns isolated synthetic storage and defaults to
ports 8186/3186. Override `MATB_SWARM_API_PORT` and `MATB_SWARM_UI_PORT` if occupied.
It refuses to adopt an existing service. For an isolated build, set
`MATB_NEXT_DIST_DIR` consistently for build, start and browser verification.

The local review used `.next/production-review` because the workstation's existing
build contained locked files. Validation environments, wheels, databases and logs
were kept in local test directories. No research data migration or live model
provider call was needed for these corrections.

## Local verification

| Check | Result |
| --- | --- |
| Frontend unit tests | 293 passed (85 files); final run used two workers to avoid resource-contention timeouts. |
| Production browser acceptance | 6 passed: desktop/mobile compilation, production page headers, browser-readable 422 responses, swarm control/replay and SAGAT concealment. |
| Hardware-accelerated swarm gate | 2 passed with `MATB_SWARM_GPU=1` and `MATB_SWARM_REQUIRE_PERFORMANCE=1`. |
| Native OpenMATB tests | 854 passed. |
| Root integration/scientific suite | 957 tests verified, 7 skipped, across the broad run and corrected export reruns; includes deterministic replay soaks and scientific contracts. |
| Full backend suite | 523 passed, 1 skipped; includes analysis, station admission, simulation, backup and restored-study execution. |
| Focused backend regressions | 46 passed, including log redaction and request/lifecycle compatibility; all 7 logging tests passed in a final rerun covering the actual Uvicorn access formatter. |
| Frontend production build, lint, TypeScript | Passed. |
| Documentation verification | Passed. |
| Dependency audits | Python: 86 project packages, zero known vulnerabilities. npm: zero known vulnerabilities. |
| Windows dependency lock | All installed constraints satisfied; `pip install --dry-run --ignore-installed` successfully resolved the complete lock. |

The broad root run initially reported 951 passes and six export failures because
its temporary output was inside the repository. Export tests correctly require
an external destination. All 11 export tests were then verified outside the
repository (10 in the subset run, one in a focused rerun after replacing an
internal route-list assumption with FastAPI's public OpenAPI schema). These
results are combined coverage, not a claim of one entirely green root invocation.
The original four logging tests are covered by the 46-test focused run. A final
seven-test logging rerun additionally verifies that redaction preserves the
structured arguments required by Uvicorn's access formatter.

The functional browser run used Chromium 151 with SwiftShader. A separate run
enabled the repository's hardware performance gate using Intel Iris Xe / D3D11
at 1920 x 1080. It recorded 576 frame samples and a 20.6 ms render interval p95,
passing the 33.3 ms threshold. This verifies that software rendering criterion
on this workstation; it does not measure physical display onset or qualify a
different workstation. See the release runbook for the full study rig procedure.
Remote Linux/Windows CI and a live deployment were not executed by this local review.
