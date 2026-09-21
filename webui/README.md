# MATB Research Console (webui)

Researcher console for protocol-defined longitudinal MATB studies. ASTRA uses
12 participants × 3 visits × 3 workload levels. Backend: `backend/` (FastAPI) and frontend: `frontend/`
(Next.js) are both implemented. The console covers participant setup, CSV +
scenario-manifest ingestion, completeness tracking, block provenance review,
descriptive visualization, confirmatory/Bayesian analysis, baseline screen
administration, and reproducible research-bundle export.

The design system mirrors the HRV "Mission Control" console for visual consistency.

## Native sUAS operations console

The same `webui` tree also serves the native synthetic sUAS command-and-control
simulator. It is Linux/headless-first and can run without X11, Docker, a GPU,
or a Windows host. The simulator is research-only and non-kinetic: it has no
real-aircraft control or weapon integration. The optional `/colombia` explorer
adds national geographic layers and read-only observed traffic. Six local
scenes provide Three.js mission views; prepared assets and captured traffic
work offline. Live observations are available in exploration and technical
sessions, while research uses checksum-pinned recordings. See the
[geography guide](../docs/implementation/colombia-geography-traffic.md) and
[verification report](../docs/implementation/colombia-geography-verification.md).

From the repository root, the supported offline install and launcher are:

```bash
MATB_VENV="$PWD/.venv-suas" bash scripts/install_suas.sh
MATB_VENV="$PWD/.venv-suas" bash scripts/run_suas.sh
```

The built UI is served at `http://127.0.0.1:3100/mission/setup`; the backend
health check is `http://127.0.0.1:8000/health`. Use `--data-dir` for the
owner-only SQLite/artifact root. The launcher binds to loopback by default and
requires explicit `MATB_FRONTEND_ORIGINS` before any non-loopback bind.

The native API is documented in
[`backend/README.md`](backend/README.md), including controller leases,
observer streams, reconnect/resynchronization, lifecycle safety, checkpoint
recovery, and sealed debrief artifacts. The browser implementation and
headless test commands are in [`frontend/README.md`](frontend/README.md).

See `docs/superpowers/specs/2026-06-03-webui-phase1-data-tracker-design.md`.

## Swarm supervision

The native mission console includes the `swarm_supervision` scenario: 2, 4, 6 or
8 aircraft, atomic group tasking, procedural racing quadcopters and third-person
presentation v3. Technical sessions start at `/mission/test`; research sessions
require an explicitly frozen v3 study condition. The same renderer supports
recorded replay and conceals all operational swarm views during SAGAT.

See the [swarm guide](../docs/implementation/suas-swarm-supervision.md) and
[release runbook](../docs/implementation/suas-swarm-release.md). The 2D/CLI service
can run without a GPU; fluid 3D presentation requires a qualified graphics-enabled
browser on the operator workstation. Use production builds for deployment.

The [2026-09-21 production review](../docs/implementation/production-readiness-2026-09-21.md)
records the current hardening changes, verified Windows dependency lock, browser
acceptance command and deployment limits.
