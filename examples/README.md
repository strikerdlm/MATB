# MATB examples

[English](README.md) | [Español](README.es.md)

Choose only the workflow you need. Every committed fixture is synthetic and
pseudonymous; no example contains real participant data, operational telemetry,
credentials, private keys, controller leases, signatures, or institutional
decisions. Examples write only to their documented default or caller-selected
output directory. Stop any service before cleanup and delete only that dedicated
example output—never a shared study, evidence, release, or acceptance store.

| Workflow | Guide | Speed and connectivity | Additional runtime |
| --- | --- | --- | --- |
| OpenMATB research | [Generate, convert, and fit](openmatb-research/README.md) | Fast and offline after Python dependencies; the tour does not start OpenMATB | A separate external OpenMATB runtime is needed only for task presentation |
| Research Console | [Local API/browser walkthrough](research-console/README.md) | Service procedure; local and offline-capable after Python/npm install and frontend build | FastAPI on 8000, browser UI on 3100 |
| Synthetic sUAS | [CLI and lifecycle walkthrough](suas-simulator/README.md) | CLI is fast/offline; service procedure is local/offline-capable after install | Browser service uses Linux/WSL2 launcher; native Windows can run CLI/call WSL2 service |
| FAC ISR SMS | [Package capability tour](sms-platform/README.md) | Package tour is fast/offline after install/build | Docker/Linux containers only for offline image/bundle procedures |
| Legacy monitor | [Four terminal modes](legacy-monitor/README.md) | Offline terminal simulation | No browser or service; experiment mode writes selected artifacts |

The words *pass*, *blocked*, or *verified* in example output describe only the
tested synthetic component contract. They do not establish clinical validity,
airworthiness, dispatch authority, operational readiness, or institutional
acceptance. Do not weaken evidence, freshness, hash, signature, privacy,
no-C2, or separation checks when a deliberately fail-closed example is blocked.

From the repository root, validate the documentation, platform entry-point
pairs, links, fixture safety, and command contracts offline:

```bash
python -m pytest tests/documentation/test_documentation.py -q
python scripts/verify_documentation.py
```

Those dependency-light checks run from a clean checkout; SMS build smoke tests
skip with an actionable message when their prepared dependencies are absent.
To include the SMS-specific build and package-tour smoke target, prepare it
explicitly:

```bash
cd SMS
npm ci
npm run build:packages
cd ..
python -m pytest tests/documentation/test_documentation.py -q -k sms_package
```

The complete install/configure/run/verify/cleanup sequence for each workflow is
in the linked guide. The root [README](../README.md) provides the prerequisite
matrix, native Windows versus WSL2 boundaries, full module catalog, operations,
troubleshooting, and governance constraints.
