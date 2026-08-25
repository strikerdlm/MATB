# SMS Operational-Core Technical Release Candidate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Follow TDD for every behavior change.

**Goal:** Deliver `fac-isr-sms@0.2.0-rc.1` as an offline, technically production-grade operational-core release for Ubuntu 24.04 x86-64 and native Windows 11/Server 2022+ x86-64 while retaining `operationalReady=false` until institutional acceptance.

**Architecture:** One same-origin Fastify process serves a live React console and authenticated API. The server derives accountable identity from secure sessions, computes safety from verified active packages, commits business state and the audit chain atomically to SQLite, and fails into read-only safe mode. Platform-specific native bundles share the same Node 22.23.2 application; Linux also retains the hardened OCI appliance.

**Tech Stack:** Node.js 22.23.2, TypeScript, Fastify, Node built-in SQLite, React 19, Vite, Vitest, Playwright, PowerShell, systemd, Docker/OCI.

**Spec:** Approved in-chat plan from 2026-08-24; original product authority remains `SMS/docs/superpowers/specs/2026-08-08-fac-isr-sms-design.md`.

## Global Constraints

- Scope is `SMS/` plus SMS-specific workflows and documentation only.
- Release identifier is `fac-isr-sms@0.2.0-rc.1`; supported native targets are `linux-x64` and `win32-x64`; OCI remains `linux/amd64`.
- Runtime Node is exactly `22.23.2`.
- Support both standalone loopback HTTPS and isolated tactical-LAN HTTPS with a required client CA/mTLS.
- Never accept identity, role, client session, safety status, or a trust key as authoritative request-body facts.
- No API, adapter, event, UI action, or package may introduce aircraft command-and-control.
- Production builds contain no realistic mission, gate, telemetry, evidence, identity, or research fixtures.
- State-changing operations, their server-computed evaluation, and audit append are atomic; failure produces no partial operational state.
- `technicalReady` and `operationalReady` are independent; this RC always reports `operationalReady=false` until the existing institutional workflow closes it.
- Offline admin CLI bootstrap is mandatory; no unauthenticated web bootstrap and no browser package upload.
- Certificates, client CAs, package trust anchors, runtime export keys, and release-signing keys stay outside the repository.
- Existing schema-v1 data is backed up and migrated; upgrade never overwrites its only copy.
- Preserve existing no-C2, research separation, deterministic verification, bilingual, and acceptance-evidence behavior.

---

### Task 1: Enforce authenticated HTTP principals and role separation

**Purpose:** Close the anonymous-access and caller-identity P0 defect before extending any operational workflow.

**Files:** Modify the Edge API auth/session/server/routes/services and their tests. Add focused HTTP auth middleware/routes as separate files. Update package exports only where consumers require them.

**Interfaces:**

- Produce `AuthenticatedPrincipal { userId, roles, missionIds, sessionId, csrfToken, requiresReauthentication, clientCertificateFingerprint? }`.
- Add `POST /api/auth/login`, `GET /api/auth/session`, `POST /api/auth/reauthenticate`, `POST /api/auth/lock`, and `POST /api/auth/logout`.
- Use cookie `__Host-sms_session` with `Secure; HttpOnly; SameSite=Strict; Path=/`; unsafe authenticated requests also require exact `x-csrf-token`.
- Session defaults: idle 15 minutes, maximum lifetime 8 hours, signing re-authentication interval 5 minutes. Identity lockout: five failed attempts for 15 minutes.
- All operational routes require a principal. Reads require mission assignment or reviewer visibility. Mission create/revise requires commander or safety-officer. Checklist responses require an assigned crew identity. Gate decisions require the exact assigned gate role and fresh re-authentication. Administrators have no implicit gate authority.
- Change service signatures so actor/session context is a separate typed parameter derived by the server. Reject request bodies containing `actorUserId`, `actorRole`, `clientSessionId`, or equivalent accountable-identity fields.
- `buildServer` accepts injected identity/session dependencies for real tests; production defaults contain no users and no test bypass.

**TDD and acceptance:**

1. Add route tests showing existing anonymous mission/gate/checklist/package/export/postflight requests succeed; run them and capture the expected RED failures against the desired 401/403 behavior.
2. Add tests for cookie flags, CSRF, idle/max expiry, lock/logout, persistent login lockout contract, mission scoping, exact gate-role separation, admin gate denial, body-identity rejection, and server-derived audit identity.
3. Implement the minimum middleware/routes/service context changes.
4. Run focused Edge API tests, then all Edge API tests, root typecheck, lint, build, and full Vitest once.

### Task 2: Compute safety server-side and establish trusted package state

**Purpose:** Close the forged-ready P0 defect and make verified local packages the only safety authority.

**Files:** Modify mission/safe-mode services, package and mission routes, safety integration, database-facing package state, and tests. Add focused policy/evaluation interfaces.

**Interfaces:**

- Remove `safetyResult` from accepted mission/revision input. Explicitly reject it rather than silently ignoring it.
- Add an injected `SafetyEvaluationProvider` that resolves the active policy, requirements, terminology, evidence snapshot, and package identities, invokes `evaluateMission`, and returns an immutable evaluation envelope.
- Evaluation envelope fields: revision ID, kernel version, policy/terminology/evidence package IDs and versions, canonical input SHA-256, evidence snapshot SHA-256, result SHA-256, evaluated UTC time, evaluations, blockers, and status.
- Recompute on creation and every material revision. Package activation marks existing evaluations stale and invalidates approvals until recomputed.
- Replace request-provided `publicKeyPem` trust with configured `TrustedKeyRecord { keyId, scope, algorithm, publicKeyPem, addedAtUtc, addedByUserId }`. Package import identifies `keyId`; unknown, wrong-scope, expired, tampered, downgraded, partial, traversal, or symlinked packages quarantine/fail closed.
- Network clients may list active/quarantined package state but cannot import or activate packages. Those mutations are CLI-only in Task 3.

**TDD and acceptance:**

1. Add failing tests that submit a forged empty `ready` result, supply an attacker key with an attacker-signed package, activate an unknown key, change a package after evaluation, and attempt a gate with stale evaluation.
2. Implement provider/trusted-key/package-state boundaries and server-owned evaluation.
3. Prove every forged/stale case remains blocked and valid injected policy fixtures produce deterministic hashes.
4. Run safety-kernel, evidence, Edge API, security/no-C2, data-separation, typecheck, lint, build, and full Vitest once.

### Task 3: Add schema v2, atomic domain persistence, readiness, and admin bootstrap

**Purpose:** Replace volatile identities and JSON-only mission persistence with recoverable, transactional production state.

**Files:** Modify database schema/migrations, identity/session persistence, audit and mission repositories, config/readiness, and tests. Add a focused `sms-admin` CLI and backup/migration utilities.

**Interfaces:**

- Schema v2 tables cover identities, credential versions/salts/hashes, roles, mission assignments, login lockout state, trusted keys, packages, active package roles, missions, revisions, evaluation envelopes, checklist responses, gate decisions, postflight records, occurrences, audit events, and a runtime lease.
- Migrate `service_state.mission_store` into normalized tables. Before migration, run integrity checks and create `<database>.pre-v2-<UTC>.sqlite`; on any failure restore schema-v1 bytes and retain the backup.
- Add a transaction/repository boundary that stages domain changes, server evaluation, and audit event, commits under `BEGIN IMMEDIATE`, then publishes in-memory state. Enforce unique gate/checklist/revision constraints in SQLite.
- Verify audit chain and database integrity on startup and before approval writes. Corruption or write failure activates read-only safe mode.
- `/healthz` is liveness only. `/readyz` reports `technicalReady`, `operationalReady`, and checks for database, migration, audit, TLS, export key, trust anchors, active policy/terminology, and bootstrap administrator. HTTP 200 requires technical readiness only.
- CLI commands: `init`, `users create|disable|assign`, `trust add|list`, `packages import|activate|list`, `backup create|verify|restore`, and `diagnose`. Bootstrap/state-changing commands require the service stopped and an exclusive runtime lease; secrets are prompted or read from protected files, never command-line values.

**TDD and acceptance:**

1. Add failing migration, rollback, concurrency, duplicate decision, audit-write fault, corruption, safe-mode, runtime-lease, CLI-secret, backup/restore, and readiness tests.
2. Implement schema/repositories/migration/CLI in small red-green cycles.
3. Prove schema-v1 fixtures survive migration and rollback, transactions cannot leave audit/business state split, and restart reloads identities/missions/evaluations.
4. Run Edge API/integration/security tests, CLI smoke tests, typecheck, lint, build, and full Vitest once.

### Task 4: Harden telemetry, signed export, transport, errors, and runtime lifecycle

**Purpose:** Complete the non-UI operational API and service lifecycle without expanding into C2.

**Files:** Modify telemetry/export/server/config/start scripts and tests. Add focused transport, signing, security-header, logging, and lifecycle modules.

**Interfaces:**

- Remove the production `/api/telemetry/replay` route. Keep replay as a test/development adapter unavailable in production builds.
- Add adapter-authenticated read-only telemetry ingestion that requires an allowlisted mTLS certificate identity, validates bounded canonical events and monotonic sequence, and cannot represent or emit command-shaped operations.
- Keep authorized SSE telemetry for assigned operational roles, observers, and reviewers; bound replay windows and disconnect resources cleanly.
- Sign mission exports with an externally provisioned Ed25519 runtime key and include release ID, revision/evaluation/package/audit hashes, signature key ID, and detached signature. Commander or reviewer plus fresh re-authentication is required.
- Resolve console/data paths portably from config/module locations. Add strict body limits, security headers/CSP, request IDs, sanitized stable errors, JSON logs without sensitive payloads, graceful SIGINT/SIGTERM shutdown, and portable configuration validation.
- Tactical mode requires server certificate/key/client CA and rejects unverified clients. Standalone remains HTTPS loopback only.

**TDD and acceptance:**

1. Add failing tests for unauthenticated/non-mTLS ingestion, replay route absence, malformed/out-of-order/oversized telemetry, SSE authorization/cleanup, export tamper/signature/role/reauth, CSP/headers, sanitized 500 errors, Windows path containment, and graceful shutdown.
2. Implement minimum behavior, preserving no-C2 scans.
3. Run Edge API, telemetry, export, security, typecheck, lint, build, and full Vitest once.

### Task 5: Replace the fixture console with a live operational-core UI

**Purpose:** Make the packaged console an honest client of the secured Edge API.

**Files:** Refactor the console app shell, add typed same-origin API/session/state modules and operational screens, update unit/E2E tests and Playwright server harness.

**Interfaces:**

- Production UI includes login/lock, mission list/current revision, server-computed safety strip, per-item checklists, four role-separated gates, package/readiness state, read-only telemetry, audit health, and signed export.
- Remove production mission/gate/map/telemetry/research fixtures. Test fixtures enter only through test props/servers. Deferred fleet, planning, assurance, research, reports, documents, and notes controls are disabled and labeled “Not included in 0.2.0-rc.1”.
- Use only same-origin `fetch`/SSE, include CSRF automatically on unsafe calls, never cache credentials/tokens in browser storage, lock on 401/session expiry, and show explicit loading/disconnected/stale/blocked/forbidden/safe-mode states.
- The release UI must never label data verified/current/nominal unless the API says so.

**TDD and acceptance:**

1. Replace fixture assertions with failing real-client component tests and a Playwright flow using a real temporary HTTPS Edge API.
2. E2E provisions distinct maintainer/operator/safety/commander identities, logs in separately, creates/revises a mission, observes server blocking, records itemized checklists and four gates, receives telemetry, exports, restarts, and verifies persistence/audit.
3. Retain bilingual, keyboard, reduced-motion, tablet/desktop, axe, and no-console-error coverage.
4. Run console unit tests, typecheck, build, E2E/a11y twice for flake detection, and full Vitest once.

### Task 6: Ship native Linux, native Windows, and hardened OCI bundles

**Purpose:** Provide repeatable offline installation, supervision, upgrade, and recovery on both required operating systems.

**Files:** Add platform packaging/install scripts and fixtures; modify Docker/Compose/offline bundle tooling and tests. Do not commit downloaded runtime binaries or generated bundles.

**Interfaces:**

- Artifacts: `fac-isr-sms-0.2.0-rc.1-linux-x64.tar.gz`, `fac-isr-sms-0.2.0-rc.1-win32-x64.zip`, and `fac-isr-sms-0.2.0-rc.1-linux-amd64.oci.tar`.
- Each native bundle carries the official Node 22.23.2 runtime, built app/static assets, production dependencies, CLI, config template, notices, SBOM fragment, and hash inventory.
- Linux installs immutable files under `/opt/fac-isr-sms`, config under `/etc/fac-isr-sms`, data under `/var/lib/fac-isr-sms`, a dedicated unprivileged account, and a hardened systemd unit. Upgrade backs up/migrates before swapping immutable files; uninstall preserves data by default.
- Windows PowerShell installs immutable files under `Program Files`, mutable config/data/logs under `ProgramData`, grants only Local Service/admin access, validates TLS key ACLs, registers an at-startup Task Scheduler job with restart policy, and supports status/stop/upgrade/uninstall with data preservation. Native Windows must not require WSL2 or Docker.
- OCI adds a privileged one-time init/preflight command that creates/chowns mounted data paths and validates TLS ownership/mode before the permanent UID/GID 10001 read-only service starts.

**TDD and acceptance:**

1. Add behavior tests that execute packagers/installers against temporary prefixes on their native CI OS; do not test scripts by grepping source.
2. Test clean install, bad ACL/TLS rejection, start/readiness, restart recovery, upgrade/migration, backup/restore, and uninstall-with-data-preservation on Ubuntu and Windows.
3. Test OCI init, rootless/read-only runtime, internal network, mounts, health/readiness, and shutdown on Linux.
4. Verify every bundled file against inventory and run offline/no-network cold-start checks.

### Task 7: Establish truthful cross-platform CI, release evidence, and operator documentation

**Purpose:** Prevent stale evidence or a development artifact from being represented as a release.

**Files:** Modify SMS package scripts, SMS CI/release workflows, release/bundle scripts, README/install/operator documentation, known limitations, and release tests.

**Interfaces:**

- `verify:ci`: clean build, typecheck, lint, all tests, real-console E2E/a11y, no-C2, data separation, and candidate artifact inventories on Ubuntu and Windows.
- `verify:technical-release`: requires exact source commit, platform artifact inventories, SBOM/scans, valid detached release signature, clean native/OCI smoke evidence, and `technicalReady=true`; any stale/missing attestation exits nonzero and emits no production-named bundle.
- `verify:operational`: existing institutional verifier with `--require-ready`; remains failing for this RC and is never conflated with technical readiness.
- CI uses Ubuntu 24.04 and Windows Server 2022 runners. OCI jobs are Linux-only. Tag/manual release workflow consumes externally supplied signature material without storing private keys in the repository.
- Archive `0.1.0` evidence as historical or regenerate only from its exact source; the current stale inventory cannot be treated as current release evidence.
- Documentation gives separate standalone, tactical, Linux native, Windows native, OCI, bootstrap, backup, upgrade, rollback, diagnostics, and limitations procedures, always retaining `operationalReady=false` language.

**TDD and acceptance:**

1. Add failing release tests for stale source inventory, absent signature, development-bundle naming, cross-platform manifest mismatch, and accidental `operationalReady=true` claims.
2. Implement scripts/workflows/docs and regenerate only unsigned deterministic fixtures used by tests.
3. Run `npm ci`, build, typecheck, lint, full Vitest, console E2E/a11y twice, native package tests, OCI tests where Docker is available, `verify:ci`, and `verify:technical-release` against a controlled signed fixture.
4. Confirm `verify:operational --require-ready` exits nonzero for the documented open limitations.

