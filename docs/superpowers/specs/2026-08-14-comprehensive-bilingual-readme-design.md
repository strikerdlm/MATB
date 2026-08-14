# Comprehensive Bilingual README and Examples Design

**Date:** 2026-08-14  
**Status:** Approved for implementation planning  
**Primary audience:** First-time users and researchers  
**Languages:** English and Spanish  
**Supported documentation environments:** Linux and Windows, with WSL2 used where POSIX behavior is the supported contract

## Context

The root `README.md` explains much of the Python/OpenMATB research workflow, the research console, the synthetic sUAS simulator, and the legacy monitor, but it predates the complete FAC ISR Safety Management System under `SMS/`. It also mixes historical status notes, setup instructions, capability descriptions, and research background in a way that makes it difficult for a first-time user to determine which application to install and which commands apply to that application.

The repository now contains several related but independently runnable systems:

- OpenMATB-compatible scenario generation, provenance, log conversion, questionnaires, and analysis;
- the Suhir DEPDF human-nonfailure and mission-outcome model;
- the FastAPI and Next.js Research Console;
- a synthetic, non-kinetic sUAS supervisory simulator;
- the FAC ISR SMS TypeScript monorepo, including an edge API, operator console, safety packages, offline bundle tooling, release verification, and institutional-review packet generation; and
- the legacy aircraft-monitoring demonstration.

The documentation must explain these surfaces as one research and safety-assurance repository without implying that every user must install every subsystem.

## Goals

1. Replace the root README with a newcomer-oriented guide that accurately explains what the repository is for, what each application does, and what it explicitly does not do.
2. Provide complete, mirrored English and Spanish guides through `README.md` and `README.es.md`.
3. Give Linux and Windows users a truthful path through installation, configuration, execution, verification, shutdown, cleanup, and troubleshooting.
4. Document every current module using repository source, package manifests, CLI parsers, route definitions, and launch scripts as the authority.
5. Add runnable, deterministic, synthetic examples that demonstrate the main capabilities without real participant data, aircraft control, operational telemetry, private keys, or institutional signatures.
6. Add offline documentation checks that detect broken internal links, missing referenced files, invalid example fixtures, and drift between the English and Spanish structures.

## Non-goals

- Do not change application behavior, APIs, safety logic, statistical methods, release evidence, or operational-readiness state.
- Do not vendor or redistribute the external OpenMATB runtime.
- Do not claim native Windows support for POSIX-only launchers; document WSL2 instead.
- Do not create real-world aircraft-control, weapon, targeting, autonomous-command, or external-telemetry examples.
- Do not include real participant identifiers, health information, operational records, credentials, private keys, or controlled institutional evidence.
- Do not manufacture reviewer decisions or imply that automated verification constitutes institutional acceptance.
- Do not duplicate detailed scientific evidence reviews or regulatory source material already maintained under `docs/`; link to those sources from a readable summary.

## Deliverables

### Root guides

- `README.md`: complete English guide and default repository landing page.
- `README.es.md`: complete Spanish guide with the same headings, anchors, commands, tables, warnings, and examples.
- A visible language switch at the beginning of both files.

### Runnable examples

Create a top-level `examples/` tree:

```text
examples/
├── README.md
├── README.es.md
├── openmatb-research/
├── research-console/
├── suas-simulator/
├── sms-platform/
└── legacy-monitor/
```

Each workflow directory will contain concise English and Spanish instructions and the smallest useful set of synthetic inputs or scripts. Bash and PowerShell entry points will be paired where the underlying module supports both environments. WSL2 instructions will be explicit for POSIX-only paths.

### Documentation verification

- Add an offline documentation verification script and focused tests.
- Verify internal Markdown links and referenced repository paths.
- Verify that English and Spanish guides share the same top-level information architecture.
- Validate JSON and other structured synthetic fixtures.
- Run fast, non-GUI example smoke tests where execution is deterministic and dependency-safe.
- Confirm documented CLI help and package-script names against the repository.

## Information Architecture

Both root guides will use the same order.

### 1. Identity and safety boundary

Explain that MATB is a military-aviation human-factors research and safety-assurance repository. Distinguish its four active surfaces:

1. OpenMATB-compatible research tooling;
2. Research Console and synthetic sUAS simulator;
3. FAC ISR SMS offline safety-management platform; and
4. the retained legacy monitor.

State prominently that the repository is not a clinical device, certified operational system, real aircraft-control channel, weapon system, or substitute for accountable human approval.

### 2. Workflow chooser

Provide a decision table that maps user intent to the correct directory, runtime, quick start, and expected output. A first-time user should be able to choose one workflow without installing unrelated modules.

### 3. Architecture and data flow

Show a compact repository tree and separate data-flow descriptions for:

- external OpenMATB session to CSV to metrics to statistical/DEPDF analysis;
- browser to Research Console backend to local research store and exports;
- synthetic sUAS scenario to supervisory session to replay/debrief artifacts; and
- signed evidence and local telemetry to edge API, safety kernel, console, audit ledger, and disconnected verification.

### 4. Prerequisites matrix

List supported versions and purpose for Python, Node.js, npm, Git, Docker, Chromium/Playwright, OpenMATB, and WSL2. Each dependency will be marked required, optional, or workflow-specific. Commands will be separated into Linux Bash and Windows PowerShell blocks.

### 5. Guided quick starts

Provide independent quick starts for:

1. OpenMATB research workflow;
2. Research Console;
3. synthetic sUAS simulator;
4. FAC ISR SMS platform; and
5. legacy monitor.

Every quick start follows the same sequence: prerequisites, install, configure, run, synthetic example, expected result, verification, stop/cleanup, and troubleshooting.

### 6. Complete module catalog

Each module entry answers:

- What does it do?
- Who should use it?
- What does it consume and produce?
- What does it depend on?
- How is it run on Linux?
- How is it run on Windows or WSL2?
- Which example demonstrates it?
- Which command verifies it?
- What safety, privacy, scientific, or operational limitation applies?

The catalog covers all of the following.

#### Python/OpenMATB research modules

- `matb_integration/scenario_builder.py`
- `matb_integration/scenario_manifest.py`
- `matb_integration/log_converter.py`
- `matb_integration/questionnaires/`
- `matb_integration/analysis/`, including frequentist and Bayesian engines
- `matb_integration/suhir/`
- `matb_integration/screen/`

#### Research Console and simulator

- `webui/backend/`
- `webui/frontend/`
- `matb_integration/suas/`
- scenario, session, stream, controller-lease, replay, debrief, and artifact workflows

#### FAC ISR SMS applications

- `SMS/apps/edge-api/`
- `SMS/apps/console/`

#### FAC ISR SMS packages

- `SMS/packages/evidence/`
- `SMS/packages/energy/`
- `SMS/packages/fleet/`
- `SMS/packages/geo/`
- `SMS/packages/human-performance/`
- `SMS/packages/research/`
- `SMS/packages/safety-kernel/`
- `SMS/packages/sms/`
- `SMS/packages/telemetry/`

#### FAC ISR SMS tools and release workflows

- `SMS/tools/map-packager/`
- `SMS/tools/research/`
- offline bundle build and verification;
- no-command-path and data-separation verification;
- signed manifest, SBOM, and release verification;
- verification matrix and operational-readiness checks; and
- unsigned institutional-review packet generation and human-supplied decision intake.

#### Legacy module

- `aircraft_monitor/`

### 7. Operations and maintenance

Document test suites, build commands, offline deployment, generated-data locations, controlled cleanup, environment variables, ports, troubleshooting, security boundaries, institutional acceptance, repository map, glossary, references, contribution guidance, and license.

## Examples Design

### General contract

All examples will:

- use deterministic seeds and synthetic identifiers;
- write only to a documented example output or temporary directory;
- avoid external networking unless the workflow explicitly requires a separately installed OpenMATB runtime;
- be safe to repeat;
- show expected output or a verification assertion;
- include cleanup instructions; and
- avoid undocumented dependencies.

### OpenMATB research examples

Demonstrate scenario generation, manifest inspection, synthetic session-log conversion, DEPDF fitting across three workload levels, and frequentist/Bayesian CLI input shapes. The external OpenMATB runner remains a separately installed dependency and will not be simulated as if vendored.

### Research Console examples

Demonstrate backend and frontend startup, health checks, synthetic participant creation, synthetic block ingestion, tracker inspection, analysis requests, and export retrieval. Use `curl` on Linux and `Invoke-RestMethod` on Windows.

### Synthetic sUAS examples

Demonstrate offline installation, local launch, health and scenario discovery, controller-lease handling, an observer-safe state request, session lifecycle, and artifact verification. Secret lease values must never be printed in URLs or committed outputs. POSIX launcher instructions use Linux or WSL2.

### FAC ISR SMS examples

Demonstrate the built package interfaces with synthetic objects and local files:

- evidence hashing and manifest validation;
- energy reserve calculations;
- fleet capability and qualification evaluation;
- coordinate/route/airspace/weather freshness checks;
- canonical telemetry replay and degradation handling;
- safety-kernel applicability, lifecycle, risk, and fail-closed gate evaluation;
- SMS hazard, audit, CAPA, ERP, indicator, and management-of-change flows;
- privacy-minimized human-performance controls;
- research consent, protocol, sensor/MATB adapter, replay, and export boundaries;
- edge API and console development startup;
- map-package validation;
- research evidence package verification;
- offline bundle construction and no-network verification; and
- unsigned acceptance-review packet generation.

Examples must not set `operationalReady=true`, insert institutional signatures, or demonstrate bypasses around blockers.

### Legacy monitor examples

Demonstrate combined, UAV, fighter, and headless experiment modes with deterministic seeds and a documented output directory.

## Linux and Windows Strategy

### Linux

Linux is the reference environment for headless operation, offline launchers, Docker verification, Bash scripts, and CI-equivalent commands.

### Windows

Use native PowerShell for Python modules, Node.js workspaces, HTTP examples, and supported frontend/backend development commands. Use WSL2 for POSIX-only sUAS launchers, shell verification scripts, Linux container workflows, and commands whose safety contract depends on Unix permissions or paths.

The documentation will never translate a Bash command mechanically into PowerShell when the resulting workflow has not been shown to preserve the same behavior.

## Safety and Governance Rules

1. The sUAS simulator is synthetic, non-kinetic, and cannot command a real aircraft or weapon system.
2. Research examples contain no real participant or health data.
3. Research outputs are exploratory unless a cited method and validated study design support stronger claims.
4. SMS automated checks do not constitute legal, safety, cybersecurity, command, or operational approval.
5. Institutional decisions require named, qualified human reviewers, controlled artifacts, exact UTC times, and validated hashes.
6. Acceptance examples remain unsigned and keep `operationalReady=false`.
7. Private keys, controller leases, credentials, absolute controlled paths, and sensitive operational data must not appear in examples or committed output.

## Error Handling and Troubleshooting Design

Each quick start will include symptom-oriented troubleshooting for the failures a newcomer is most likely to encounter:

- wrong Python or Node version;
- inactive virtual environment;
- missing external OpenMATB installation;
- OpenMATB Pyglet/display problems;
- Windows execution-policy or path quoting issues;
- WSL2 filesystem and port-access confusion;
- occupied backend/frontend ports;
- missing Chromium/Playwright browser;
- unavailable Docker daemon;
- invalid or expired evidence packages;
- stale, missing, or tampered SMS inputs;
- readiness remaining blocked after tests pass; and
- attempting to record an unsigned acceptance template.

Troubleshooting must preserve fail-closed behavior. It must not recommend disabling validation, bypassing signatures, exposing non-loopback services without explicit configuration, or weakening file permissions.

## Verification Strategy

### Documentation checks

- Verify every relative Markdown link and referenced path offline.
- Verify the English and Spanish root guides contain the same ordered major sections.
- Reject placeholders such as `TBD`, `TODO`, fake paths presented as real, or undocumented environment variables.
- Validate JSON fixtures with the standard library.
- Verify shell and PowerShell example pairs are present where promised.

### Executable example checks

- Run deterministic Python examples that do not require a GUI or external OpenMATB runtime.
- Build the SMS workspace before running Node examples against compiled package exports.
- Run fast package examples and assert their expected result shape.
- Exercise API examples through existing automated API tests rather than starting an uncontrolled long-running service in documentation tests.
- Treat browser, Docker, and external OpenMATB examples as integration procedures and verify their commands against existing CI or dedicated test suites.

### Existing regression suites

Use the relevant existing Python, backend, frontend, sUAS, and SMS test commands after documentation and example changes. Documentation-only verification does not replace application regression tests when executable examples import production modules.

## Maintenance Rules

- Commands in the README must refer to package scripts or checked-in launchers rather than copied implementation details when possible.
- English and Spanish headings must remain structurally synchronized.
- Example outputs must be regenerated only from deterministic synthetic inputs.
- Historical phase notes belong in the changelog or roadmap; the root README describes current repository behavior.
- Module status must be derived from merged code and tests, not stale pull-request numbers.
- Detailed specialist documentation remains authoritative for advanced workflows; the root README links to it without forcing first-time users to discover basic setup elsewhere.

## Acceptance Criteria

The work is complete when:

1. A first-time Linux or Windows user can identify the correct workflow without reading source code.
2. Both root READMEs comprehensively and consistently explain the repository and every current module.
3. Each primary workflow has an install-to-verification sequence and at least one synthetic example.
4. Every documented command is traced to a current script, manifest, CLI, route, or tested workflow.
5. Internal links and structured examples pass offline verification.
6. Fast runnable examples pass their smoke tests.
7. Existing affected regression suites pass.
8. The documentation preserves all research, privacy, no-C2, fail-closed, and institutional-acceptance boundaries.
9. No user-owned unrelated changes are included.

