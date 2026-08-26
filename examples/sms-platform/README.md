# FAC ISR SMS capability tour

[Español](README.es.md)

This executable tour exercises the public, compiled FAC ISR SMS package boundaries with synthetic data. It prints one deterministic JSON document. It does not start a service, command an aircraft, approve a mission, record an institutional decision, or establish operational readiness. The deliberately incomplete hard requirement keeps `safetyKernel.status` blocked, and the research event remains non-dispatchable.

## Prerequisites and quick start

Use Node.js 22.x and the lockfile in `SMS/package-lock.json`. From a networked development workstation, `npm ci` may download locked dependencies; on an isolated workstation it succeeds only when the npm cache is already populated. After dependency installation and package compilation, the tour itself reads local files and performs no network I/O.

Linux or WSL:

```bash
./examples/sms-platform/run.sh
```

Native Windows with PowerShell 7+:

```powershell
./examples/sms-platform/run.ps1
```

The runners change to `SMS/`, run `npm ci`, build all packages, and then run `node ../examples/sms-platform/package-tour.mjs`. You can repeat the final Node command to confirm identical output. Generated `SMS/packages/*/dist` trees and `SMS/node_modules` are local build products and must not be committed.

## What the result demonstrates

The nine top-level objects map directly to the nine packages. Evidence hashes a controlled local fixture. Energy calculates a reserve from the complete approved-performance input shape. Fleet evaluates a qualified VLOS capability against accepted evidence. Geo builds a stable route segment. Telemetry replays a fixed delayed event as read-only data. The safety kernel rejects a hard requirement with no accepted source evidence. SMS promotes a synthetic hazard and evaluates an SPI while audit, CAPA, ERP, and management-of-change examples remain blocked or incomplete when accountable evidence is absent. Human performance applies an explicit policy. Research opens a consented pseudonymous session, adapts one MATB event, and exports a deidentified record without operational identity or release fields.

Passing energy or fleet checks are component results, not flight authorization. The summary contains no human acceptance, signing material, credential, or mission-release decision.

## Workspace roles

| Workspace | Role and boundary |
| --- | --- |
| `SMS/packages/evidence/` | Canonical JSON, hashes, source records, claims, manifests, downgrade rejection, and package verification. |
| `SMS/packages/energy/` | Unit-labelled battery/segment parsing and deterministic mission-energy/reserve evaluation using an evidence-backed performance model. |
| `SMS/packages/fleet/` | Aircraft configuration, capability evidence, maintenance release, and crew qualification evaluation. |
| `SMS/packages/geo/` | Coordinates, signed offline geo packages, terrain, visibility, routes, airspace, weather, and non-transmitting flight-plan drafts. |
| `SMS/packages/telemetry/` | Strict read-only telemetry canonicalization, delayed/dropout handling, replay, and retention provenance; it has no command path. |
| `SMS/packages/safety-kernel/` | Deterministic applicability, freshness, fleet/energy facts, risk, lifecycle, gates, and append-only audit decisions; unknown hard evidence fails closed. |
| `SMS/packages/sms/` | Organizational hazards, safety-performance indicators, audits, CAPA, emergency-response readiness, and management of change. |
| `SMS/packages/human-performance/` | Duty/qualification/fatigue status, workload, alert load, and CRM briefing boundaries. |
| `SMS/packages/research/` | Protocol, ethics/consent, instruments, MATB/sensor adapters, replay, aggregation, and deidentified exports separated from operations. |
| `SMS/apps/edge-api/` | Local Fastify API, database/audit services, safe-mode package intake, and non-C2 data boundaries. |
| `SMS/apps/console/` | React reviewer console and accessibility/end-to-end tests. |
| `SMS/tools/map-packager/` | Offline geo-manifest inspection, construction, controlled signing, and verification. |
| `SMS/tools/research/` | Source acquisition/copy, extraction, checksum and offline evidence verification, query logging, and source-level no-C2 scanning. |

## Build, test, typecheck, and lint

Run workspace-wide quality gates from `SMS/`:

```bash
cd SMS
npm run build
npm test
npm run typecheck
npm run lint
```

`npm run build` compiles packages, tools, the edge API, and console. `npm test` has a pretest build and then runs the Vitest workspace. Typecheck uses the root TypeScript project; lint uses the root ESLint configuration. Individual workspaces expose `build`, `test`, and `typecheck`, for example `npm test --workspace @fac-isr/sms`. The console additionally provides `test:e2e` and `test:a11y` and requires installed Playwright browser assets for those checks.

## Local development applications

The edge API package intentionally has no `dev` script. Build it, then start its exported server explicitly for local-only development. This command uses an in-memory database, disabled internet mode, no TLS, and the loopback edge port used by the deployment manifest; do not expose it beyond the workstation:

```bash
cd SMS
npm run build --workspace @fac-isr/edge-api
node --input-type=module -e 'import("./apps/edge-api/dist/server.js").then(async ({buildServer}) => { const app = await buildServer({bindAddress:"127.0.0.1", port:8443, databaseUrl:":memory:", packageDirectory:"./data/packages", internet:"disabled"}); await app.listen({host:"127.0.0.1", port:8443}); })'
```

The endpoint is development-only HTTP at `http://127.0.0.1:8443/healthz`; readiness normally remains not ready because controlled packages and institutional configuration are absent.

For the console development server:

```bash
cd SMS/apps/console
npm run dev
```

Vite normally selects loopback port 5173 for development. The package's controlled preview command binds `127.0.0.1:4173`, which is also the Playwright manifest URL:

```bash
cd SMS/apps/console
npm run preview:test
```

Build before `preview:test` when it was not invoked through its pre-script. Application startup is a development demonstration, not acceptance evidence.

## Offline edge deployment

`SMS/Dockerfile` produces a pinned `linux/amd64` Linux container. `SMS/docker/compose.edge.yml` binds host loopback only, at `127.0.0.1:8443` by default, and uses an internal Docker network. Native Windows can run the Node/npm/PowerShell development workflow, but the offline container requires Docker Desktop or another Linux-container runtime; the Linux entrypoint uses POSIX tools and permissions and is not a native Windows service.

The Compose deployment requires three institutionally controlled host locations: `SMS_DATA_DIR` for the writable encrypted SQLite data volume, `SMS_PACKAGE_DIR` for read-only verified packages, and `SMS_TLS_DIR` containing the readable certificate and tightly permissioned private TLS material. `SMS_EDGE_PORT` may change only the loopback host port. Inside the container the database is `/var/lib/fac-isr/data/edge.sqlite`, packages are `/opt/sms/packages`, and TLS is mandatory. The runtime sets internet mode to disabled, runs as UID/GID 10001, drops capabilities, uses a read-only filesystem, and exposes only HTTPS.

Do not place controlled TLS or release material in this example or repository. Receiving institutions must provide it through their approved custody and encrypted-storage process.

The offline lifecycle commands are:

```bash
cd SMS
npm run build:offline
npm run verify:offline
npm run verify:evidence-offline
npm run verify:no-c2
npm run verify:data-separation
```

`build:offline` builds/tests the workspace and Linux image, collects the OCI archive, SBOM, acceptance evidence, and package inventories into a transfer bundle. It needs a Docker daemon plus locked npm dependencies and the pinned base image available during construction; “offline” describes the produced runtime/transfer boundary, not an automatic promise that the build workstation never needs staged inputs. `verify:offline` validates the bundle structure, hashes, image metadata, acceptance workflow, and no-network contract. `verify:evidence-offline` needs an explicit deterministic `SMS_EVIDENCE_VERIFY_AS_OF` UTC environment value and validates locally registered source artifacts. The no-C2 and data-separation checks inspect the operational/research boundary without granting readiness.

## Map and research command-line tools

Build tools with `npm run build:tools` from `SMS/`. The map parser supports:

- `inspect` with required `--directory` and optional `--manifest`;
- `build-manifest` with `--directory` and `--metadata`, plus optional `--output`;
- `sign` with `--directory`, an externally controlled signing input path, and optional `--manifest`;
- `verify` with `--directory`, a controlled public verification input, `--as-of`, and optional `--manifest`.

Invoke it as `node tools/map-packager/dist/cli.js <command>`. With no recognized command it prints its current usage and exits nonzero. Signing is a controlled release activity; the tour neither invokes it nor supplies material.

The research parser supports `record-query`, `acquire`, `copy-obsidian`, `extract`, `verify`, `verify-offline`, and `verify-no-c2`. `record-query` requires `--tool` and `--query`; status is `pending`, `executed`, or `unverified-lead`, and `executed` also requires an evidence artifact. `acquire` records an official source with source/title/authority/URI/target metadata and optional expected hash or staging file. `copy-obsidian` imports a note with source and target provenance. `extract` takes source and target paths. `verify` takes a source and expected SHA-256. The offline and no-C2 commands use the controlled workspace registers and local source trees. Invoke it as `node tools/research/dist/cli.js <command>` from `SMS/`; unknown or missing commands fail rather than guessing.

## Verification, release, and institutional acceptance

The complete command inventory from `SMS/package.json` is:

```bash
cd SMS
npm run build
npm test
npm run typecheck
npm run lint
npm run build:offline
npm run verify:offline
npm run verify:evidence-offline
npm run verify:no-c2
npm run verify:data-separation
npm run verify:ci -- --platform linux --local
npm run verify:technical-release -- --candidate <candidate-directory> --source-commit <40-hex-commit> --public-key <external-public-key.pem>
npm run verify:operational -- --require-ready
npm run verify:matrix
npm run acceptance:packets
npm run verify:acceptance
npm run verify:all
```

The bare list identifies the scripts; parameterized workflows still require their parser arguments. Linux-local `verify:ci` exercises controlled TEST-ONLY platform fixtures and does not create production evidence. Production CI runs on Ubuntu 24.04 and Windows Server 2022 against the exact official-runtime artifacts. `verify:technical-release` requires all three exact artifact names/inventories, current SBOM/scans, clean native and OCI smoke evidence, the exact source commit, a detached signature, and an externally supplied public key. It can establish `technicalReady=true` but requires `operationalReady=false` for this RC. Never create demonstration institutional signing material or commit controlled material. See the [operator guide](../../SMS/docs/operator-guide.md).

`verify:matrix` executes the evidence matrix and deliberately writes a report whose readiness remains false even when all technical requirements pass. `acceptance:packets` requires `-- --output <empty-directory> --as-of <exact-UTC>` and optionally one approved `--scope`; it generates deterministic unsigned reviewer packets outside `SMS/docs/release`. Those packets are not decisions.

`acceptance:record` is intentionally omitted from the bulk command block because it is not a routine automated check. Its dry run requires a current generated packet plus a human-supplied controlled institutional decision; applying it is a separate mutating action. Never populate a template with fabricated reviewers, approvals, timestamps, evidence, or outcomes. Qualified institutional reviewers must resolve the RACAE/translation, operational checklist, risk authority, emergency response, cybersecurity/deployment, official geospatial data, human-factors, research separation, and training/safety-promotion scopes.

`verify:operational` (the current name for the institutional verifier; `verify:acceptance` remains a compatibility alias) validates the recorded evidence as of an explicit UTC instant. `--require-ready` is the strict gate and intentionally fails for 0.2.0-rc.1 while limitations/reviews remain open. `verify:all` combines typecheck, lint, matrix generation, and acceptance verification. A passing build, test suite, matrix, or technical-release gate can coexist with `operationalReady=false`. Only the controlled human institutional workflow may change that state.

## Safety interpretation

This tour is synthetic reviewer education. “Pass” means only that one deterministic component contract accepted its supplied synthetic facts. “Blocked,” “unknown,” “expired,” and “incomplete” are expected fail-closed outcomes when evidence, freshness, authority, or human acceptance is missing. Nothing in the JSON is a dispatch instruction, command-and-control path, airworthiness finding, medical finding, or authorization to fly.
