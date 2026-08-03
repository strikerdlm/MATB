# MATB Research Console (webui)

Researcher console for the MATB longitudinal study (12 participants × 6 visits ×
3 workload levels). Backend: `backend/` (FastAPI) and frontend: `frontend/`
(Next.js) are both implemented. The console covers participant setup, CSV +
scenario-manifest ingestion, completeness tracking, block provenance review,
descriptive visualization, confirmatory/Bayesian analysis, baseline screen
administration, and reproducible research-bundle export.

The design system mirrors the HRV "Mission Control" console for visual consistency.

## Native sUAS operations console

The same `webui` tree also serves the native synthetic sUAS command-and-control
simulator. It is Linux/headless-first and can run without X11, Docker, a GPU,
or a Windows host. The simulator is research-only and non-kinetic: it has no
real aircraft, weapon, map, or telemetry integration.

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
