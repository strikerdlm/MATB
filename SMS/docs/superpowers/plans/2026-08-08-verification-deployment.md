# Verification, Security, and Offline Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not call the product operationally accepted until the institutional review evidence in the final task exists.

**Goal:** Produce a repeatable, headless offline deployment and verification package proving regulatory traceability, safe failure, data separation, accessibility, performance, package integrity, and absence of any C2 command path.

**Architecture:** CI builds and tests the complete `SMS/` workspace, creates a locked OCI image and offline transfer bundle, signs the software/SBOM/release manifest, and runs the same verification scripts on a clean disconnected node. Acceptance artifacts are immutable and include source checksums, policy version, golden results, known limitations, and qualified review records.

**Tech Stack:** npm workspaces; Node.js 22 LTS; TypeScript; Vitest; Playwright; axe-core; fast-check; Docker/OCI; Syft or approved SBOM generator; Cosign/Ed25519-compatible signing; Trivy or approved scanner; `openssl`; shell/Node verification scripts.

## Global Constraints

- The edge node must operate fully offline after a signed bundle is transferred from a connected staging workstation.
- Unclassified controlled-data banner, local TLS, least privilege, encrypted storage/backups/exports, signed packages, append-only audit, session lock, and quarantine are release requirements.
- Unauthorized package downgrade, altered historical snapshot, stale critical data, clock inconsistency, database write failure, and kernel failure fail closed.
- The release artifact must include tests and evidence for all RACAE classes, named blocked cases, material-change invalidation, bilingual equivalence, geospatial integrity, energy reserve, telemetry degradation, data separation, accessibility, and no-C2 behavior.
- No operational acceptance claim is valid without qualified FAC/AAAES review, operational checklist validation, ERP exercises, cybersecurity review, and independent acceptance of active risk matrices/delegated authorities.

## File Map

- Create: `SMS/.github/workflows/ci.yml` or equivalent local CI definition.
- Create: `SMS/Dockerfile`
- Create: `SMS/docker/compose.edge.yml`
- Create: `SMS/docker/entrypoint.sh`
- Create: `SMS/scripts/build-offline-bundle.mjs`
- Create: `SMS/scripts/verify-offline.mjs`
- Create: `SMS/scripts/verify-no-c2.mjs`
- Create: `SMS/scripts/verify-data-separation.mjs`
- Create: `SMS/scripts/generate-sbom.mjs`
- Create: `SMS/docs/release/verification-matrix.md`
- Create: `SMS/docs/release/known-limitations.md`
- Create: `SMS/docs/release/state-aviation-acceptance-checklist.md`
- Create: `SMS/docs/release/release-manifest.json`
- Create: `SMS/docs/release/release-manifest.sig`
- Create: `SMS/test/integration/*.test.ts`
- Create: `SMS/test/security/*.test.ts`
- Create: `SMS/test/performance/*.test.ts`
- Create: `SMS/test/fixtures/blocked-cases/*.json`

## Interfaces

```ts
export interface ReleaseManifest {
  version: string;
  commit: string;
  author: string;
  builtAtUtc: string;
  nodeVersion: string;
  packageIds: readonly string[];
  artifacts: readonly { path: string; sha256: string; mediaType: string }[];
  testReportSha256: string;
  sbomSha256: string;
  knownLimitationsPath: string;
  signature: string;
  keyId: string;
}

export interface VerificationReport {
  ok: boolean;
  checks: readonly { id: string; status: "pass" | "fail" | "warn"; evidence: string[] }[];
  releaseId: string;
}
```

### Task 1: Establish CI, strict build, lint, and reproducible test commands

**Files:**
- Create: `SMS/.github/workflows/ci.yml`
- Modify: `SMS/package.json`
- Create: `SMS/eslint.config.mjs`
- Create: `SMS/test/integration/build.test.ts`
- Test: CI job itself and local `SMS/test/integration/build.test.ts`

**Interfaces:**
- Produces `npm run verify:all` that runs typecheck, lint, unit, property, integration, E2E, accessibility, no-C2, and data-separation checks.

- [ ] **Step 1: Write the failing aggregate verification test**

```ts
it("requires every workspace and verification script in the release command", () => {
  const scripts = readPackageJson().scripts;
  expect(scripts).toMatchObject({
    typecheck: expect.any(String),
    test: expect.any(String),
    lint: expect.any(String),
    "verify:all": expect.any(String),
    "verify:no-c2": expect.any(String),
    "verify:data-separation": expect.any(String),
  });
});
```

- [ ] **Step 2: Run it to verify the aggregate command is missing**

Run: `cd SMS && npm test -- test/integration/build.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement strict CI and local scripts**

CI runs on a clean Node 22 environment with `npm ci`, typecheck, lint, all workspace tests, Playwright, axe, no-C2 scan, separation scan, SBOM generation, and bundle verification. Pin lockfile and tool versions; do not use network at test runtime.

- [ ] **Step 4: Run local aggregate verification and commit**

Run: `cd SMS && npm ci && npm run verify:all`
Expected: PASS or a named failing check; no command may be hidden behind `|| true`.

```bash
git add SMS/.github SMS/package.json SMS/eslint.config.mjs SMS/test/integration/build.test.ts
git commit -m "ci(sms): add reproducible verification pipeline"
```

### Task 2: Build a headless OCI image and disconnected transfer bundle

**Files:**
- Create: `SMS/Dockerfile`
- Create: `SMS/docker/compose.edge.yml`
- Create: `SMS/docker/entrypoint.sh`
- Create: `SMS/scripts/build-offline-bundle.mjs`
- Create: `SMS/scripts/verify-offline.mjs`
- Test: `SMS/test/integration/offline-install.test.ts`

**Interfaces:**
- `npm run build:offline -- --output dist/offline-bundle`
- `npm run verify:offline -- --bundle dist/offline-bundle --no-network`

- [ ] **Step 1: Write disconnected install tests**

```ts
it("starts the edge image with network access blocked", async () => {
  const result = await runContainer({ network: "none", command: ["/opt/sms/bin/healthcheck"] });
  expect(result.exitCode).toBe(0);
});

it("fails verification when a required local package is absent", async () => {
  const result = await verifyOffline("fixture-missing-terrain");
  expect(result.ok).toBe(false);
  expect(result.checks).toContainEqual(expect.objectContaining({ id: "terrain-package" , status: "fail" }));
});
```

- [ ] **Step 2: Run tests to verify image and bundle are absent**

Run: `cd SMS && npm test -- test/integration/offline-install.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement multi-stage headless image and bundle builder**

Build the console static assets and edge API into a minimal runtime image, mount signed data/package directories read-only where possible, run as a non-root user, enable local TLS, SQLite WAL, health checks, and explicit data paths. The bundle includes image digest, package artifacts, migrations, public keys, manifest, SBOM, test report, and install instructions; it includes no cloud credential or private signing key.

- [ ] **Step 4: Implement offline verifier**

With network disabled, verify image digest, release signature, package signatures/hashes/dependencies/expiry/no-downgrade, migrations, policy package, terminology, map baseline, fonts/licenses, keys, encrypted database paths, and health/ready endpoints. Write a machine-readable report and human-readable summary.

- [ ] **Step 5: Run disconnected smoke test and commit**

Run: `cd SMS && npm run build:offline -- --output dist/offline-bundle && npm run verify:offline -- --bundle dist/offline-bundle --no-network`
Expected: PASS on a clean host with network disabled.

```bash
git add SMS/Dockerfile SMS/docker SMS/scripts/build-offline-bundle.mjs SMS/scripts/verify-offline.mjs SMS/test/integration/offline-install.test.ts
git commit -m "feat(deploy): build disconnected headless edge bundle"
```

### Task 3: Generate signed release manifest and SBOM

**Files:**
- Create: `SMS/scripts/generate-sbom.mjs`
- Create: `SMS/docs/release/release-manifest.json`
- Create: `SMS/docs/release/release-manifest.sig`
- Test: `SMS/test/integration/release-manifest.test.ts`

**Interfaces:**
- `npm run release:manifest -- --version x.y.z`
- `npm run release:sign -- --key-id <id>`
- `npm run release:verify`

- [ ] **Step 1: Write manifest and SBOM tests**

```ts
it("requires hashes for every artifact and a signed manifest", () => {
  const manifest = readReleaseManifest();
  expect(manifest.signature).toBeTruthy();
  expect(manifest.artifacts.every((artifact) => /^[a-f0-9]{64}$/.test(artifact.sha256))).toBe(true);
  expect(manifest.sbomSha256).toMatch(/^[a-f0-9]{64}$/);
});
```

- [ ] **Step 2: Run test to verify release artifacts are absent**

Run: `cd SMS && npm test -- test/integration/release-manifest.test.ts --run`
Expected: FAIL.

- [ ] **Step 3: Implement SBOM, license, and provenance generation**

Generate SPDX or CycloneDX SBOM including workspace dependencies, transitive versions, licenses, source URLs, map/font licenses, and build commit. Scan the image and bundle with the approved malware/vulnerability scanner; record findings and disposition.

- [ ] **Step 4: Implement manifest signing and verification**

Sign canonical JSON with release key; include author metadata, commit, Node/tool versions, package IDs/hashes, test/SBOM hashes, known limitations, and signing key ID. Private keys never enter the repository or edge bundle.

- [ ] **Step 5: Run tests and commit**

Run: `cd SMS && npm run release:manifest -- --version 0.1.0 && npm run release:verify && npm test -- test/integration/release-manifest.test.ts --run`
Expected: PASS; changed artifact, signature, SBOM, or commit is detected.

```bash
git add SMS/scripts/generate-sbom.mjs SMS/docs/release/release-manifest.json SMS/docs/release/release-manifest.sig SMS/test/integration/release-manifest.test.ts
git commit -m "release(sms): sign software manifest and SBOM"
```

### Task 4: Prove security controls and the absence of a C2 command path

**Files:**
- Create: `SMS/scripts/verify-no-c2.mjs`
- Create: `SMS/scripts/verify-data-separation.mjs`
- Test: `SMS/test/security/no-c2.test.ts`
- Test: `SMS/test/security/package-tamper.test.ts`
- Test: `SMS/test/security/data-separation.test.ts`

**Interfaces:**
- `npm run verify:no-c2`
- `npm run verify:data-separation`

- [ ] **Step 1: Write negative security tests**

```ts
it("finds no command-looking API route, adapter method, or event", async () => {
  const result = await runNoC2Scan(".");
  expect(result.forbidden).toEqual([]);
});

it("cannot import research identity into operational storage", async () => {
  await expect(importResearchPackageIntoOperationalDb()).rejects.toThrow("data domain");
});
```

- [ ] **Step 2: Run tests to verify scanners are absent**

Run: `cd SMS && npm test -- test/security --run`
Expected: FAIL.

- [ ] **Step 3: Implement AST/text and runtime no-C2 verification**

Scan source and generated route metadata for forbidden operations (`arm`, `launch`, `sendCommand`, `redirect`, payload control, recovery control), outbound GCS transports, command-shaped messages, and unapproved network clients. Combine static scan with runtime route enumeration and adapter contract tests. Document deliberate read-only terms such as “route deviation” separately from command verbs.

- [ ] **Step 4: Implement tamper, rollback, TLS, least-privilege, and separation checks**

Modify an evidence/map/policy package, audit event, historical mission snapshot, or research record and confirm verification fails or quarantine/read-only mode activates. Assert role denial, session lock, local TLS, encrypted paths, separate database/key IDs, and no research-to-operational writes.

- [ ] **Step 5: Run security tests and commit**

Run: `cd SMS && npm run verify:no-c2 && npm run verify:data-separation && npm test -- test/security --run`
Expected: PASS; any future C2-like identifier or data-boundary bypass fails CI.

```bash
git add SMS/scripts/verify-no-c2.mjs SMS/scripts/verify-data-separation.mjs SMS/test/security
git commit -m "test(security): prove no command path and data isolation"
```

### Task 5: Execute the complete functional, human-factors, and performance matrix

**Files:**
- Create: `SMS/docs/release/verification-matrix.md`
- Create: `SMS/test/fixtures/blocked-cases/*.json`
- Create: `SMS/test/integration/state-aviation.test.ts`
- Create: `SMS/test/performance/multi-aircraft.test.ts`
- Create: `SMS/test/performance/long-duration.test.ts`
- Modify: `SMS/apps/console/e2e/*.spec.ts`

**Interfaces:**
- Produces `dist/reports/verification-report.json` and `SMS/docs/release/verification-matrix.md` with test command, result, artifact hash, reviewer, and unresolved limitation for each requirement.

- [ ] **Step 1: Populate the verification matrix from the approved design**

Cover: normalized rules/calculations, all RACAE classes, VFR/IFR, VLOS/EVLOS/BVLOS, golden blocked cases, dependency invalidation, bilingual equivalence, map projection/datum/terrain/obstacle/airspace, battery/reserve, package tamper/expiry/downgrade/partial import, telemetry delay/dropout/duplication/order/malformed, offline cold start, concurrency/gate separation, accessibility/day/night/tablet/reduced motion, long-duration/multi-aircraft performance, operational/research separation, and no-C2 negatives.

- [ ] **Step 2: Run the state-aviation integration suite**

Run: `cd SMS && npm test -- test/integration/state-aviation.test.ts --run`
Expected: PASS for unarmed ISR/support fixtures in IA, IB, IC, II, and III; IFR only where explicit approved evidence is present; all named hard blocks remain blocked.

- [ ] **Step 3: Run performance and concurrency tests**

Run: `cd SMS && npm test -- test/performance --run`
Expected: the edge node handles the configured tactical mission count and coordinated aircraft/telemetry replay without dropped audit writes, stale UI claims, or event-order corruption. Record measured hardware, duration, sample size, and limits; do not invent universal thresholds.

- [ ] **Step 4: Run accessibility and human-factors checks**

Run: `cd SMS && npm run test:e2e --workspace apps/console && npm run test:a11y --workspace apps/console`
Expected: no critical axe violations; keyboard, touch targets, contrast, focus, bilingual labels, reduced motion, day/night, and Mission Safety Strip comprehension evidence are captured.

- [ ] **Step 5: Commit the verification report**

```bash
git add SMS/docs/release/verification-matrix.md SMS/test SMS/apps/console/e2e
git commit -m "test(sms): complete state aviation verification matrix"
```

### Task 6: Assemble institutional acceptance and known-limitations evidence

**Files:**
- Create: `SMS/docs/release/state-aviation-acceptance-checklist.md`
- Create: `SMS/docs/release/known-limitations.md`
- Create: `SMS/docs/release/operational-readiness-record.json`
- Create: `SMS/docs/release/verification-signatures.jsonl`

**Interfaces:**
- Produces an explicit acceptance record, not an application state that pretends to be authority approval.

- [ ] **Step 1: Write the acceptance checklist**

Include qualified FAC review of RACAE interpretations/translations, operational checklist validation with operators/remote pilots/maintainers/safety/commanders, active matrix/delegated-authority acceptance, ERP tabletop/functional exercises, cybersecurity/deployment review, map/terrain/AIP/NOTAM data acceptance, human-factors usability protocol approval, research separation review, and training/safety-promotion readiness.

- [ ] **Step 2: Record known limitations and degraded-data procedures**

List each unsupported or uncertain aircraft capability, terrain/obstacle coverage, official data dependency, telemetry field, profile boundary, translation gap, research limitation, and required human action. Expired or missing critical data must identify the controlled exception process, not be hidden.

- [ ] **Step 3: Obtain and record signatures**

Store reviewer identity, organization/unit, role, scope, decision, UTC timestamp, evidence hashes, conflicts, conditions, and expiry/review date. Do not replace a missing institutional signature with an automated pass.

- [ ] **Step 4: Run final verification and commit**

Run: `cd SMS && npm run verify:all && npm run build:offline && npm run verify:offline -- --bundle dist/offline-bundle --no-network`
Expected: PASS with no unreviewed hard requirement, unsigned package, failing security negative, or unresolved release blocker.

```bash
git add SMS/docs/release
git commit -m "docs(release): record state aviation acceptance evidence"
```

## P6 Completion Evidence

P6 is complete when a clean headless host can install the signed bundle without internet, pass the full verification matrix, reject tampered/expired/downgraded artifacts, preserve audit and historical snapshots, enforce separated roles/data, prove no C2 path, and present qualified institutional acceptance and known limitations as evidence rather than implied software status.
