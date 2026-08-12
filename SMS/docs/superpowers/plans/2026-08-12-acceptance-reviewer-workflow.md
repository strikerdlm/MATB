# Acceptance Reviewer Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic, hash-locked institutional review packets and a fail-closed workflow that validates and atomically records human-supplied acceptance decisions without manufacturing approval.

**Architecture:** Shared ECMAScript-module contracts own acceptance schemas, path and hash validation, canonical serialization, and required-role decision-chain evaluation. A read-only packet generator and a dry-run-by-default decision recorder consume those contracts; the existing readiness and standalone offline verifiers independently confirm the resulting state. Journaled two-file updates preserve append-only history and block readiness during interrupted recovery.

**Tech Stack:** Node.js 22, ECMAScript modules, TypeScript declaration files, Vitest 3, SHA-256, Node filesystem primitives, npm workspaces.

## Global Constraints

- The real repository must retain zero institutional signatures and `operationalReady=false`; successful decisions exist only in temporary test fixtures unless a qualified human supplies actual evidence.
- Packet generation requires an exact UTC `--as-of` value. Identical repository inputs and an identical `asOfUtc` must produce byte-identical output.
- Automation may generate packets and validate syntax, but only a named human reviewer may supply an institutional decision.
- Every required reviewer role has its own append-only decision chain. One decision cannot accept a multi-role scope.
- A later role decision must supersede the current head for the same scope and role; forks, cycles, skipped heads, cross-scope supersession, cross-role supersession, and unlinked decisions fail closed.
- The institutional artifact must be a regular non-symlink file below `docs/release/acceptance-artifacts/`, contain only unclassified controlled safety metadata, and match its recorded SHA-256.
- Validation is dry-run by default. Authoritative mutation requires `--apply`; interrupted mutation requires explicit `--recover`.
- The recorder must not change known limitations, `operationalReady`, `qualification`, `recordStatus`, or `readinessDecision`.
- Reviewer PKI, records-management APIs, limitation closure, final institutional release, and P7 future profiles are out of scope.
- The disconnected bundle and verifier must work with `--no-network` and must not carry private-key material.
- Do not add runtime dependencies.

## File Map

- Create `SMS/scripts/acceptance-contracts.mjs`: canonical values, validation primitives, evidence hashing, packet hashing, and required-role decision-chain derivation.
- Create `SMS/scripts/acceptance-contracts.d.mts`: public contracts for TypeScript tests and script consumers.
- Create `SMS/scripts/generate-acceptance-review-packets.mjs` and `.d.mts`: deterministic packet library and CLI.
- Create `SMS/scripts/record-acceptance-decision.mjs` and `.d.mts`: dry-run validation, journaled apply, and recovery library and CLI.
- Create `SMS/test/integration/acceptance-contracts.test.ts`: primitives and decision-chain unit coverage.
- Create `SMS/test/integration/acceptance-review-packets.test.ts`: deterministic packet and read-only behavior.
- Create `SMS/test/integration/acceptance-decision-intake.test.ts`: dry-run, apply, failure, and recovery behavior.
- Modify `SMS/scripts/verify-operational-readiness.mjs` and `.d.mts`: consume shared contracts, validate role coverage/history, and block active transactions.
- Modify `SMS/test/integration/operational-readiness.test.ts`: use complete institutional-decision fixtures and prove multi-role semantics.
- Modify `SMS/scripts/build-offline-bundle.mjs` and `.d.mts`: generate current packets and bundle historical packet/artifact evidence.
- Modify `SMS/scripts/verify-offline.mjs`: reuse shared contracts and verify bundle mappings, role heads, and artifacts offline.
- Modify `SMS/test/integration/offline-install.test.ts`: exercise packet/artifact copying and standalone tamper detection.
- Modify `SMS/scripts/generate-sbom.mjs`: include the new workflow source and tests in future signed release inventories.
- Modify `SMS/package.json`: expose packet and intake commands.
- Modify `SMS/docs/release/state-aviation-acceptance-checklist.md`: document the coordinator workflow and required-role rule.

---

### Task 1: Canonical acceptance contracts without behavior change

**Files:**

- Create: `SMS/scripts/acceptance-contracts.mjs`
- Create: `SMS/scripts/acceptance-contracts.d.mts`
- Create: `SMS/test/integration/acceptance-contracts.test.ts`
- Modify: `SMS/scripts/verify-operational-readiness.mjs:3-139`
- Modify: `SMS/scripts/verify-operational-readiness.d.mts:19-23`

**Interfaces:**

- Consumes: Node `crypto`, `fs/promises`, and `path`; no package dependencies.
- Produces: `canonicalJson`, `sha256Bytes`, `sha256File`, `nonEmptyString`, `exactUtc`, `readJsonLines`, `resolveContainedExistingFile`, `REQUIRED_REVIEW_SCOPES`, `REVIEW_STATUSES`, `KNOWN_LIMITATION_CATEGORIES`, `ACCEPTANCE_EVIDENCE_PATHS`, and `ACCEPTANCE_STATE_PATHS`.
- Extends: `OperationalReadinessOptions` with contained candidate overrides used only by the transaction task.

- [ ] **Step 1: Write failing primitive and containment tests**

Create `acceptance-contracts.test.ts` with exact canonicalization, UTC, and filesystem cases:

```ts
import { mkdir, mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  canonicalJson,
  exactUtc,
  resolveContainedExistingFile,
  sha256Bytes,
} from "../../scripts/acceptance-contracts.mjs";

const roots: string[] = [];
afterEach(async () => Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true }))));

describe("acceptance contracts", () => {
  it("canonicalizes object keys recursively without reordering arrays", () => {
    const value = { z: [{ b: 2, a: 1 }], a: "value" };
    expect(canonicalJson(value)).toBe('{"a":"value","z":[{"a":1,"b":2}]}');
    expect(sha256Bytes(Buffer.from("verified\n"))).toBe("672eb8316fec83f94119a4193f9fc552513d56a147502f8be4830e017d817831");
  });

  it.each([
    ["2026-08-12T16:00:00Z", true],
    ["2026-08-12T16:00:00.000Z", true],
    ["2026-02-30T00:00:00Z", false],
    ["2026-08-12 16:00:00Z", false],
  ] as const)("validates exact UTC %s", (value, expected) => {
    expect(exactUtc(value)).toBe(expected);
  });

  it("rejects traversal and every symlink even when its target remains contained", async () => {
    const root = await mkdtemp(join(tmpdir(), "acceptance-contracts-"));
    roots.push(root);
    await mkdir(join(root, "docs/release"), { recursive: true });
    await writeFile(join(root, "outside.txt"), "outside\n", "utf8");
    await symlink(join(root, "outside.txt"), join(root, "docs/release/link.txt"));
    await expect(resolveContainedExistingFile(root, "../escape.txt", "evidence")).rejects.toThrow(/relative|traversal/u);
    await expect(resolveContainedExistingFile(root, "docs/release/link.txt", "evidence")).rejects.toThrow(/symbolic link/u);
  });
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `cd SMS && npx vitest run test/integration/acceptance-contracts.test.ts`

Expected: FAIL because `scripts/acceptance-contracts.mjs` does not exist.

- [ ] **Step 3: Implement the shared primitives and declarations**

Create the module with these constants and signatures:

```js
export const REQUIRED_REVIEW_SCOPES = Object.freeze([
  "cybersecurity-deployment", "emergency-response", "human-factors-protocol",
  "official-geospatial-data", "operational-checklist", "racae-interpretation-translation",
  "research-separation", "risk-authority", "training-safety-promotion",
]);
export const REVIEW_STATUSES = Object.freeze(["pending", "accepted", "accepted-with-conditions", "rejected"]);
export const ACCEPTANCE_EVIDENCE_PATHS = Object.freeze([
  "docs/release/known-limitations.md",
  "docs/release/release-manifest.json",
  "docs/release/release-manifest.sig",
  "docs/release/release-public-key.pem",
  "docs/release/sbom.cdx.json",
  "docs/release/security-scan.json",
  "docs/release/state-aviation-acceptance-checklist.md",
  "docs/release/test-report.json",
  "docs/release/verification-matrix.md",
]);
export const ACCEPTANCE_STATE_PATHS = Object.freeze([
  "docs/release/operational-readiness-record.json",
  "docs/release/verification-signatures.jsonl",
  "docs/release/state-aviation-acceptance-checklist.md",
  "docs/release/known-limitations.md",
  "docs/release/verification-matrix.md",
  "docs/release/release-manifest.json",
]);

export function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}
```

Implement `exactUtc` with calendar component round-tripping, `sha256Bytes` and streaming `sha256File`, and `readJsonLines` with line-numbered parse errors. Implement `resolveContainedExistingFile` by rejecting absolute, backslash, NUL, empty, dot, and dot-dot components; `lstat` every component below the root; reject every symbolic link; require the target to be a regular file; compare `realpath(root)` and `realpath(target)` before returning the absolute target.

Declare the exact exports in `acceptance-contracts.d.mts`. Extend readiness options as follows and keep both overrides contained under the repository root:

```ts
export interface OperationalReadinessOptions {
  readonly asOfUtc?: string;
  readonly recordRelativePath?: string;
  readonly signatureLogRelativePath?: string;
  readonly allowTransactionJournal?: boolean;
}
```

Replace the duplicated verifier primitives with imports from `acceptance-contracts.mjs`. Do not change findings, exit codes, or the current empty-ledger result.

- [ ] **Step 4: Run focused contract and readiness tests and verify GREEN**

Run: `cd SMS && npx vitest run test/integration/acceptance-contracts.test.ts test/integration/operational-readiness.test.ts`

Expected: PASS, including the existing 9-pending-review and 10-open-limitation assertions.

- [ ] **Step 5: Commit the behavior-preserving extraction**

```bash
git add SMS/scripts/acceptance-contracts.mjs SMS/scripts/acceptance-contracts.d.mts SMS/scripts/verify-operational-readiness.mjs SMS/scripts/verify-operational-readiness.d.mts SMS/test/integration/acceptance-contracts.test.ts
git commit -m "refactor(sms): centralize acceptance contracts"
```

### Task 2: Required-role decision chains and readiness verification

**Files:**

- Modify: `SMS/scripts/acceptance-contracts.mjs`
- Modify: `SMS/scripts/acceptance-contracts.d.mts`
- Modify: `SMS/scripts/verify-operational-readiness.mjs:141-398`
- Modify: `SMS/scripts/verify-operational-readiness.d.mts`
- Modify: `SMS/test/integration/acceptance-contracts.test.ts`
- Modify: `SMS/test/integration/operational-readiness.test.ts`

**Interfaces:**

- Consumes: Task 1 primitives and the readiness record's `requiredReviewerRoles` and `signatureIds`.
- Produces: `InstitutionalDecision`, `RequiredReview`, `ReviewDecisionState`, `signatureRecordFailure(decision)`, and `deriveReviewDecisionState(review, decisions)`.

- [ ] **Step 1: Write failing multi-role history tests**

Add a fixture helper that creates full schema records:

```ts
import { createHash } from "node:crypto";

const packetFixture = "fixture packet\n";
const artifactFixture = "fixture institutional artifact\n";
const packetSha256 = createHash("sha256").update(packetFixture).digest("hex");
const artifactSha256 = createHash("sha256").update(artifactFixture).digest("hex");

function decision(scope: string, role: string, id: string, overrides: Record<string, unknown> = {}) {
  return {
    schemaVersion: "1.0",
    recordType: "institutional-decision",
    signatureId: id,
    sourcePacketId: "a".repeat(64),
    sourcePacketPath: `docs/release/acceptance-packets/${"a".repeat(64)}.json`,
    sourcePacketSha256: packetSha256,
    supersedesSignatureId: null,
    releaseId: "fac-isr-sms@0.1.0",
    reviewer: { identity: `reviewer-${id}`, identityType: "human", organizationUnit: "FAC", role },
    scope,
    decision: "accept",
    signedAtUtc: "2026-08-12T15:00:00.000Z",
    evidenceHashes: [{ path: "evidence/verification.txt", sha256: "672eb8316fec83f94119a4193f9fc552513d56a147502f8be4830e017d817831" }],
    conflicts: [],
    conditions: [],
    reviewDueAtUtc: "2027-08-12T15:00:00.000Z",
    systemOfRecordRef: "FAC-RMS:fixture-001",
    institutionalArtifact: { path: "docs/release/acceptance-artifacts/fixture.json", sha256: artifactSha256 },
    ...overrides,
  };
}
```

Extend the temporary-repository fixture to create `docs/release/acceptance-packets/<64-a>.json` with `packetFixture` and `docs/release/acceptance-artifacts/fixture.json` with `artifactFixture`, both as regular files. This lets readiness verification check the actual source-packet and institutional-artifact hashes instead of bypassing them.

Test a risk-authority review requiring `designated risk authority` and `commander`:

```ts
it("keeps a multi-role scope pending until every required role accepts", () => {
  const review = {
    scope: "risk-authority",
    status: "pending",
    requiredReviewerRoles: ["designated risk authority", "commander"],
    signatureIds: ["risk-1"],
  };
  const state = deriveReviewDecisionState(review, [decision("risk-authority", "designated risk authority", "risk-1")]);
  expect(state).toMatchObject({ status: "pending", missingRoles: ["commander"] });
});

it("derives rejection immediately and rejects a forked supersession chain", () => {
  const first = decision("risk-authority", "commander", "cmd-1");
  const rejection = decision("risk-authority", "commander", "cmd-2", { decision: "reject", supersedesSignatureId: "cmd-1" });
  expect(deriveReviewDecisionState(reviewWith(["cmd-1", "cmd-2"]), [first, rejection]).status).toBe("rejected");
  const fork = decision("risk-authority", "commander", "cmd-3", { supersedesSignatureId: "cmd-1" });
  expect(deriveReviewDecisionState(reviewWith(["cmd-1", "cmd-2", "cmd-3"]), [first, rejection, fork]).violations)
    .toContainEqual(expect.objectContaining({ code: "DECISION_CHAIN_FORK" }));
});
```

Add separate cases for unconditional full-role acceptance, conditional precedence, a cycle, skipped/current-head supersession, cross-role supersession, cross-scope supersession, an unlinked ledger decision, an unknown required role, and a record status that disagrees with the derived status.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `cd SMS && npx vitest run test/integration/acceptance-contracts.test.ts test/integration/operational-readiness.test.ts`

Expected: FAIL because `deriveReviewDecisionState` is not exported and the verifier does not enforce required-role coverage.

- [ ] **Step 3: Implement decision schemas, chains, and derived status**

Use these declaration contracts:

```ts
export type AcceptanceDecision = "accept" | "accept-with-conditions" | "reject";
export type ReviewStatus = "pending" | "accepted" | "accepted-with-conditions" | "rejected";
export interface EvidenceHash { readonly path: string; readonly sha256: string; }
export interface InstitutionalDecision {
  readonly schemaVersion: "1.0";
  readonly recordType: "institutional-decision";
  readonly signatureId: string;
  readonly sourcePacketId: string;
  readonly sourcePacketPath: string;
  readonly sourcePacketSha256: string;
  readonly supersedesSignatureId: string | null;
  readonly releaseId: string;
  readonly reviewer: { readonly identity: string; readonly identityType: "human"; readonly organizationUnit: string; readonly role: string };
  readonly scope: string;
  readonly decision: AcceptanceDecision;
  readonly signedAtUtc: string;
  readonly evidenceHashes: readonly EvidenceHash[];
  readonly conflicts: readonly string[];
  readonly conditions: readonly string[];
  readonly reviewDueAtUtc: string;
  readonly systemOfRecordRef: string;
  readonly institutionalArtifact: EvidenceHash;
}
export interface RequiredReview {
  readonly scope: string;
  readonly status: ReviewStatus;
  readonly requiredReviewerRoles: readonly string[];
  readonly signatureIds: readonly string[];
}
export interface ReviewDecisionState {
  readonly status: ReviewStatus;
  readonly missingRoles: readonly string[];
  readonly roleHeads: readonly { readonly role: string; readonly signatureId: string; readonly decision: AcceptanceDecision }[];
  readonly violations: readonly { readonly code: string; readonly scope: string; readonly detail: string }[];
}
```

Validate all decision fields, including exact role membership, packet/artifact paths and hashes, human identity, conditions, conflicts, and increasing times. Build one directed chain per required role, where edges point from a decision to `supersedesSignatureId`. Reject missing parents, forks, cycles, and scope/role changes. Derive status with this literal precedence:

```js
const headDecisions = roleHeads.map(({ decision }) => decision);
const status = headDecisions.includes("reject")
  ? "rejected"
  : missingRoles.length > 0
    ? "pending"
    : headDecisions.includes("accept-with-conditions")
      ? "accepted-with-conditions"
      : "accepted";
```

In `verifyOperationalReadiness`, reject an active `docs/release/.acceptance-transaction.json` unless `allowTransactionJournal` is true. Validate every ledger decision and its evidence, require every decision ID to appear exactly once in its matching review, derive each review status independently, emit `REVIEW_ROLE_MISSING`, `DECISION_CHAIN_*`, `SIGNATURE_UNLINKED`, or `REVIEW_STATUS_DERIVATION_MISMATCH`, and preserve all existing blocker semantics.

Update old test helpers so accepted fixture records contain one decision per required role rather than one decision per scope. Keep the real repository assertion at zero signatures.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `cd SMS && npx vitest run test/integration/acceptance-contracts.test.ts test/integration/operational-readiness.test.ts`

Expected: PASS with multi-role, history-integrity, current blocked-release, and prior validation coverage.

- [ ] **Step 5: Commit the role-complete gate**

```bash
git add SMS/scripts/acceptance-contracts.mjs SMS/scripts/acceptance-contracts.d.mts SMS/scripts/verify-operational-readiness.mjs SMS/scripts/verify-operational-readiness.d.mts SMS/test/integration/acceptance-contracts.test.ts SMS/test/integration/operational-readiness.test.ts
git commit -m "feat(sms): require complete reviewer role decisions"
```

### Task 3: Deterministic reviewer packet generation

**Files:**

- Create: `SMS/scripts/generate-acceptance-review-packets.mjs`
- Create: `SMS/scripts/generate-acceptance-review-packets.d.mts`
- Create: `SMS/test/integration/acceptance-review-packets.test.ts`

**Interfaces:**

- Consumes: Task 1 hashes/canonicalization/path lists, Task 2 role derivation, `verifyOperationalReadiness`, the readiness record, and checklist.
- Produces: `generateAcceptanceReviewPackets(root, output, options)`, `ReviewPacketManifest`, `UnsignedDecisionTemplate`, and CLI options `--output`, `--as-of`, and optional `--scope`.

- [ ] **Step 1: Write failing deterministic, complete, and read-only tests**

Create a temporary output directory and hash both authoritative files before generation:

```ts
const options = { asOfUtc: "2026-08-12T16:00:00.000Z" } as const;
const before = await authoritativeHashes(smsRoot);
const first = await generateAcceptanceReviewPackets(smsRoot, join(root, "first"), options);
const second = await generateAcceptanceReviewPackets(smsRoot, join(root, "second"), options);

expect(first.packets).toHaveLength(9);
expect(await directoryDigest(join(root, "first"))).toBe(await directoryDigest(join(root, "second")));
expect(await authoritativeHashes(smsRoot)).toEqual(before);
for (const packet of first.packets) {
  expect(packet.manifest.recordType).toBe("review-packet");
  expect(packet.manifest.asOfUtc).toBe(options.asOfUtc);
  expect(packet.manifest.requiredReviewerRoles.length).toBeGreaterThan(0);
  expect(packet.manifest.blockers.length).toBe(19);
  expect(packet.template.recordType).toBe("unsigned-decision-template");
  expect(packet.template.signatureId).toBeNull();
}
```

Also test one selected scope, unknown scope rejection, missing/invalid `asOfUtc`, changed readiness-record bytes changing `acceptanceStateFingerprint`, and a packet ID equal to the SHA-256 of its canonical manifest with `packetId` omitted.

- [ ] **Step 2: Run the packet test and verify RED**

Run: `cd SMS && npx vitest run test/integration/acceptance-review-packets.test.ts`

Expected: FAIL because the generator module does not exist.

- [ ] **Step 3: Implement packet contracts and generation**

Declare the generator interface:

```ts
export interface GenerateReviewPacketOptions {
  readonly asOfUtc: string;
  readonly scopes?: readonly string[];
}
export interface ReviewPacketManifest {
  readonly schemaVersion: "1.0";
  readonly recordType: "review-packet";
  readonly packetId: string;
  readonly releaseId: string;
  readonly readinessRecordId: string;
  readonly asOfUtc: string;
  readonly scope: string;
  readonly title: string;
  readonly requiredReviewerRoles: readonly string[];
  readonly currentStatus: "pending" | "accepted" | "accepted-with-conditions" | "rejected";
  readonly roleCoverage: readonly { readonly role: string; readonly signatureId: string | null; readonly decision: "accept" | "accept-with-conditions" | "reject" | null }[];
  readonly checklistHeading: string;
  readonly blockers: readonly { readonly code: string; readonly scope?: string; readonly limitationId?: string; readonly detail: string }[];
  readonly acceptanceStateFingerprint: string;
  readonly evidence: readonly { readonly path: string; readonly sha256: string }[];
}
export interface UnsignedDecisionTemplate {
  readonly schemaVersion: "1.0";
  readonly recordType: "unsigned-decision-template";
  readonly signatureId: null;
  readonly sourcePacketId: string;
  readonly sourcePacketPath: string;
  readonly sourcePacketSha256: string;
  readonly supersedesSignatureId: null;
  readonly releaseId: string;
  readonly scope: string;
  readonly reviewer: { readonly identity: null; readonly identityType: "human"; readonly organizationUnit: null; readonly role: null };
  readonly decision: null;
  readonly signedAtUtc: null;
  readonly evidenceHashes: readonly { readonly path: string; readonly sha256: string }[];
  readonly conflicts: null;
  readonly conditions: null;
  readonly reviewDueAtUtc: null;
  readonly systemOfRecordRef: null;
  readonly institutionalArtifact: { readonly path: null; readonly sha256: null };
}
export function generateAcceptanceReviewPackets(
  root: string,
  output: string,
  options: GenerateReviewPacketOptions,
): Promise<{ readonly packetCount: number; readonly packets: readonly { readonly manifest: ReviewPacketManifest; readonly template: UnsignedDecisionTemplate }[] }>;
```

Use an explicit scope-to-heading map for the nine numbered checklist sections. Extract each section from its heading through the next `## ` heading. Hash `ACCEPTANCE_EVIDENCE_PATHS` into a sorted inventory. Hash the sorted `{ path, sha256 }` records for `ACCEPTANCE_STATE_PATHS` to form `acceptanceStateFingerprint`. Call `verifyOperationalReadiness(root, { asOfUtc })` for current blockers. Build the manifest without `packetId`, hash its canonical JSON, add the ID, and write all JSON with two-space indentation plus one trailing newline. Write fixed-order Markdown without a generation-time clock.

The unsigned template must include the immutable release, packet, scope, packet archive path, and packet file hash but must set human-controlled fields to null:

```js
const template = {
  schemaVersion: "1.0",
  recordType: "unsigned-decision-template",
  signatureId: null,
  sourcePacketId: manifest.packetId,
  sourcePacketPath: `docs/release/acceptance-packets/${manifest.packetId}.json`,
  sourcePacketSha256: sha256Bytes(Buffer.from(packetJson, "utf8")),
  supersedesSignatureId: null,
  releaseId: manifest.releaseId,
  scope: manifest.scope,
  reviewer: { identity: null, identityType: "human", organizationUnit: null, role: null },
  decision: null,
  signedAtUtc: null,
  evidenceHashes: manifest.evidence,
  conflicts: null,
  conditions: null,
  reviewDueAtUtc: null,
  systemOfRecordRef: null,
  institutionalArtifact: { path: null, sha256: null },
};
```

Parse CLI arguments strictly, reject an existing nonempty output directory, print a one-line PASS result, and use top-level `await main().catch(...)` so buffered output is not lost.

- [ ] **Step 4: Run packet and readiness tests and verify GREEN**

Run: `cd SMS && npx vitest run test/integration/acceptance-review-packets.test.ts test/integration/operational-readiness.test.ts`

Expected: PASS; generation yields nine packets and does not alter readiness evidence.

- [ ] **Step 5: Commit the packet generator**

```bash
git add SMS/scripts/generate-acceptance-review-packets.mjs SMS/scripts/generate-acceptance-review-packets.d.mts SMS/test/integration/acceptance-review-packets.test.ts
git commit -m "feat(sms): generate institutional review packets"
```

### Task 4: Dry-run human decision validation

**Files:**

- Create: `SMS/scripts/record-acceptance-decision.mjs`
- Create: `SMS/scripts/record-acceptance-decision.d.mts`
- Create: `SMS/test/integration/acceptance-decision-intake.test.ts`

**Interfaces:**

- Consumes: packet manifests from Task 3 and decision/role/hash contracts from Tasks 1-2.
- Produces: `validateAcceptanceDecision(root, packetPath, decisionPath, options)`, `AcceptanceDecisionValidation`, and CLI options `--packet`, `--decision`, `--as-of`, and `--apply`.

- [ ] **Step 1: Write failing dry-run and rejection tests**

Generate a risk-authority packet in a temporary repository, create a regular fixture artifact below the allowed directory, and write a completed decision. Assert that dry-run succeeds without changing authoritative hashes:

```ts
const report = await validateAcceptanceDecision(root, packetPath, decisionPath, {
  asOfUtc: "2026-08-12T16:00:00.000Z",
});
expect(report).toMatchObject({
  ok: true,
  mode: "dry-run",
  scope: "risk-authority",
  requiredRole: "designated risk authority",
  projectedStatus: "pending",
});
expect(await authoritativeHashes(root)).toEqual(before);
```

Use `it.each` to reject the unsigned template, automation identity, unknown role, release mismatch, scope mismatch, packet ID/hash mismatch, changed acceptance-state fingerprint, changed evidence list, duplicate signature ID, malformed system-of-record reference, future signing time, expired review time, conditional decision without conditions, unconditional decision with conditions, artifact outside the allowed directory, symlink artifact, missing artifact, and artifact hash mismatch. Every row must assert unchanged authoritative hashes.

- [ ] **Step 2: Run intake tests and verify RED**

Run: `cd SMS && npx vitest run test/integration/acceptance-decision-intake.test.ts`

Expected: FAIL because the recorder module does not exist.

- [ ] **Step 3: Implement validation and strict CLI parsing**

Declare this report:

```ts
export interface AcceptanceDecisionValidation {
  readonly ok: boolean;
  readonly mode: "dry-run";
  readonly signatureId: string;
  readonly scope: string;
  readonly requiredRole: string;
  readonly projectedStatus: "pending" | "accepted" | "accepted-with-conditions" | "rejected";
  readonly packetId: string;
  readonly artifactSha256: string;
}
export interface DecisionValidationOptions { readonly asOfUtc: string; }
export function validateAcceptanceDecision(
  root: string,
  packetPath: string,
  decisionPath: string,
  options: DecisionValidationOptions,
): Promise<AcceptanceDecisionValidation>;
```

Read both input files as regular non-symlink files. Reject every record type except `institutional-decision`. Rebuild and validate the packet ID, recompute the current acceptance-state fingerprint, require the decision evidence array to equal the packet evidence array byte-for-byte after canonicalization, and verify every evidence hash. Require `signedAtUtc <= asOfUtc < reviewDueAtUtc`. Accept `systemOfRecordRef` only when trimmed, 1-512 characters, and free of ASCII control characters. Resolve the artifact with `resolveContainedExistingFile`, then require its repository-relative path to begin with `docs/release/acceptance-artifacts/` and its hash to match.

Reject an existing signature ID. For `supersedesSignatureId: null`, reject an existing head for the same scope and role; for a non-null value, require it to be that exact head. Project the review state by appending the candidate in memory and calling `deriveReviewDecisionState`.

The CLI must require all three value arguments, remain dry-run unless `--apply` is present, return exit 2 for argument errors, exit 1 for validation errors, and print JSON with `--json`. Defer the `--apply` branch to Task 5 by throwing `--apply is not available until transaction support is initialized` after argument validation; tests in this task invoke the library dry-run only.

- [ ] **Step 4: Run intake, packet, and readiness tests and verify GREEN**

Run: `cd SMS && npx vitest run test/integration/acceptance-decision-intake.test.ts test/integration/acceptance-review-packets.test.ts test/integration/operational-readiness.test.ts`

Expected: PASS for dry-run validation and every fail-closed row.

- [ ] **Step 5: Commit dry-run intake**

```bash
git add SMS/scripts/record-acceptance-decision.mjs SMS/scripts/record-acceptance-decision.d.mts SMS/test/integration/acceptance-decision-intake.test.ts
git commit -m "feat(sms): validate institutional decisions"
```

### Task 5: Journaled apply and deterministic recovery

**Files:**

- Modify: `SMS/scripts/record-acceptance-decision.mjs`
- Modify: `SMS/scripts/record-acceptance-decision.d.mts`
- Modify: `SMS/scripts/verify-operational-readiness.mjs`
- Modify: `SMS/test/integration/acceptance-decision-intake.test.ts`
- Modify: `SMS/test/integration/operational-readiness.test.ts`

**Interfaces:**

- Consumes: Task 4 validated decision and Task 1 candidate-path verifier options.
- Produces: `recordAcceptanceDecision(root, packetPath, decisionPath, options)`, `recoverAcceptanceTransaction(root, options)`, append-only ledger updates, packet archives, and transaction journal behavior.

- [ ] **Step 1: Write failing apply, immutability, concurrency, and crash tests**

Add a successful apply test and assert exact boundaries. When testing multiple role decisions, regenerate the scope packet after every apply because each ledger update changes the acceptance-state fingerprint:

```ts
const beforeRecord = JSON.parse(await readFile(recordPath, "utf8"));
const result = await recordAcceptanceDecision(root, packetPath, decisionPath, {
  asOfUtc: "2026-08-12T16:00:00.000Z",
  apply: true,
});
const afterRecord = JSON.parse(await readFile(recordPath, "utf8"));
expect(result).toMatchObject({ ok: true, mode: "applied", projectedStatus: "pending" });
expect(afterRecord.requiredReviews.find(({ scope }: { scope: string }) => scope === "risk-authority").signatureIds).toEqual(["risk-fixture-1"]);
for (const field of ["knownLimitations", "operationalReady", "qualification", "recordStatus", "readinessDecision"] as const) {
  expect(afterRecord[field]).toEqual(beforeRecord[field]);
}
expect((await readFile(ledgerPath, "utf8")).trim().split("\n")).toHaveLength(1);
```

Add tests that all required roles produce `accepted` only after the final role decision, a second decision appends and supersedes without deleting the first, concurrent lock acquisition fails, and an existing journal blocks readiness verification.

Inject a programmatic `failpoint: "after-ledger-replace"` to emulate process death. Assert the journal remains, `operationalReady=false`, and ordinary verification reports `ACCEPTANCE_TRANSACTION_INCOMPLETE`. Run recovery and assert both files return to their original hashes. Add final-state recovery (both candidate hashes), no-op recovery (both original hashes), and unknown-hash refusal.

- [ ] **Step 2: Run intake and readiness tests and verify RED**

Run: `cd SMS && npx vitest run test/integration/acceptance-decision-intake.test.ts test/integration/operational-readiness.test.ts`

Expected: FAIL because apply and recovery are not implemented.

- [ ] **Step 3: Implement lock, candidate validation, commit journal, and recovery**

Use these exact transaction contracts:

```ts
export type AcceptanceFailpoint = "after-packet-install" | "after-ledger-replace" | "after-record-replace";
export interface RecordDecisionOptions {
  readonly asOfUtc: string;
  readonly apply: true;
  readonly failpoint?: AcceptanceFailpoint;
}
export type AcceptanceApplyReport = Omit<AcceptanceDecisionValidation, "mode"> & { readonly mode: "applied"; readonly transactionId: string };
export interface RecoveryReport { readonly ok: true; readonly action: "finalized" | "rolled-back" | "cleaned-original"; readonly transactionId: string; }
export function recordAcceptanceDecision(
  root: string,
  packetPath: string,
  decisionPath: string,
  options: RecordDecisionOptions,
): Promise<AcceptanceApplyReport>;
export function recoverAcceptanceTransaction(
  root: string,
  options: { readonly asOfUtc: string },
): Promise<RecoveryReport>;
```

The journal JSON at `docs/release/.acceptance-transaction.json` contains `schemaVersion`, `transactionId`, exact relative paths, and original/candidate hashes for the ledger and record. The transaction directory `docs/release/.acceptance-transactions/<transactionId>/` contains byte-for-byte originals and candidates. Set `transactionId` to the SHA-256 of canonical JSON containing the candidate signature ID plus the candidate record and ledger hashes; do not place the raw signature ID in a path and do not use random or wall-clock values.

Acquire `docs/release/.acceptance-update.lock` with `open(path, "wx", 0o600)` and write the transaction ID into it before commit. After Task 4 validation, reread every source, ensure its hash is unchanged, archive the canonical packet with exclusive creation or exact-byte equality, build the candidate ledger by appending one canonical JSON line, append the signature ID to the matching review, and assign only its derived status. Validate candidates using:

```js
const candidateReport = await verifyOperationalReadiness(root, {
  asOfUtc,
  recordRelativePath: candidateRecordRelative,
  signatureLogRelativePath: candidateLedgerRelative,
  allowTransactionJournal: true,
});
if (!candidateReport.ok) throw new Error(`candidate acceptance state is invalid: ${JSON.stringify(candidateReport.violations)}`);
```

Fsync candidate files, originals, transaction directory, and journal before individual `rename` operations. Fsync `docs/release` after each rename. Remove journal, transaction directory, and lock only after final verification succeeds. Ordinary caught errors attempt rollback; failpoint errors deliberately preserve the journal and transaction directory for recovery tests.

Implement `--recover` as a mutually exclusive CLI mode requiring `--as-of` but no packet or decision. It may take over an existing lock only when that lock names the same transaction as the journal; any other lock remains a hard failure. Compare both authoritative hashes with journal hashes: finalize candidates when both are candidate; clean the transaction when both are original; restore both original files when mixed; reject any unrecognized hash. Validate after recovery before deleting the journal, transaction directory, and matching stale lock.

- [ ] **Step 4: Run focused transaction and readiness tests and verify GREEN**

Run: `cd SMS && npx vitest run test/integration/acceptance-decision-intake.test.ts test/integration/operational-readiness.test.ts`

Expected: PASS for dry-run, apply, complete role coverage, append-only supersession, lock contention, crash blocking, and all recovery states.

- [ ] **Step 5: Commit transactional intake**

```bash
git add SMS/scripts/record-acceptance-decision.mjs SMS/scripts/record-acceptance-decision.d.mts SMS/scripts/verify-operational-readiness.mjs SMS/test/integration/acceptance-decision-intake.test.ts SMS/test/integration/operational-readiness.test.ts
git commit -m "feat(sms): record acceptance decisions transactionally"
```

### Task 6: Disconnected bundle integration and standalone verification

**Files:**

- Modify: `SMS/scripts/build-offline-bundle.mjs:1-207,378-445`
- Modify: `SMS/scripts/build-offline-bundle.d.mts`
- Modify: `SMS/scripts/verify-offline.mjs:1-193,519-611`
- Modify: `SMS/test/integration/offline-install.test.ts`
- Modify: `SMS/scripts/generate-sbom.mjs:38-66`

**Interfaces:**

- Consumes: Task 3 packet generation, Task 2 decision-chain validation, and Task 5 archived packet/artifact references.
- Produces: `copyAcceptanceEvidence(stage, { asOfUtc })`, bundle `acceptanceEvidence.workflow`, `reports/acceptance/reviewer-packets/`, `reports/acceptance/review-evidence/`, and `reports/acceptance/recorded-decisions/`.

- [ ] **Step 1: Write failing bundle inventory and tamper tests**

Update the copy test to pass a fixed time and require nine packet manifests:

```ts
const evidence = await copyAcceptanceEvidence(stage, { asOfUtc: "2026-08-12T16:00:00.000Z" });
expect(evidence.workflow.currentPackets).toHaveLength(9);
expect(evidence.workflow.recordedDecisions).toEqual([]);
for (const packet of evidence.workflow.currentPackets) {
  expect(await readFile(join(stage, packet.path), "utf8")).toContain(`"packetId": "${packet.packetId}"`);
}
```

Create a fixture bundle with one valid recorded decision, its archived packet, artifact, and source-to-bundle evidence mappings. Assert the standalone verifier accepts the evidence while keeping readiness blocked. Then mutate each of: current packet, historical packet, artifact, role-head metadata, and source-to-bundle mapping. Each mutation must produce an `institutional-acceptance` failure. Add an incomplete-journal fixture and assert failure.

- [ ] **Step 2: Run offline tests and verify RED**

Run: `cd SMS && npx vitest run test/integration/offline-install.test.ts`

Expected: FAIL because bundle workflow metadata and packet directories are absent.

- [ ] **Step 3: Implement bundle copying and standalone validation**

Change the exported interface to:

```ts
export interface BundledAcceptanceWorkflow {
  readonly currentPackets: readonly { readonly scope: string; readonly packetId: string; readonly path: string; readonly sha256: string }[];
  readonly evidenceMappings: readonly { readonly sourcePath: string; readonly bundlePath: string; readonly sha256: string }[];
  readonly recordedDecisions: readonly {
    readonly signatureId: string;
    readonly scope: string;
    readonly role: string;
    readonly sourcePacketPath: string;
    readonly packetBundlePath: string;
    readonly sourcePacketSha256: string;
    readonly artifactSourcePath: string;
    readonly artifactBundlePath: string;
    readonly artifactSha256: string;
  }[];
  readonly roleHeads: readonly { readonly scope: string; readonly role: string; readonly signatureId: string; readonly decision: string }[];
}
export function copyAcceptanceEvidence(stage: string, options: { readonly asOfUtc: string }): Promise<BundledAcceptanceEvidence>;
```

Generate current packets directly into the stage with `asOfUtc: builtAtUtc`. Copy every fixed packet evidence source into `reports/acceptance/review-evidence/` and record a unique sorted source-to-bundle mapping. For every ledger decision, copy its archived packet and artifact into `reports/acceptance/recorded-decisions/` using hash-prefixed filenames; reject symlinks, duplicate destinations with different bytes, missing files, or hash mismatches. Copy `acceptance-contracts.mjs` beside `bin/verify-offline.mjs` and import it from the standalone verifier.

In `verify-offline.mjs`, validate the workflow object against bundled files, recompute packet IDs, check packet and artifact hashes, resolve decision evidence through `evidenceMappings`, reconstruct role chains with `deriveReviewDecisionState`, and require workflow role heads to equal the derived sorted heads. Preserve warnings for truthful blocked states and fail any active journal marker.

Add these files to `BASE_ARTIFACTS` in `generate-sbom.mjs` so the next signed release inventory covers the intake implementation: all six new `.mjs`/`.d.mts` workflow files, `acceptance-contracts.test.ts`, `acceptance-review-packets.test.ts`, `acceptance-decision-intake.test.ts`, and `offline-install.test.ts`. Keep the already-listed readiness and release-manifest tests.

- [ ] **Step 4: Run offline, packet, intake, and release-manifest tests and verify GREEN**

Run: `cd SMS && npx vitest run test/integration/offline-install.test.ts test/integration/acceptance-review-packets.test.ts test/integration/acceptance-decision-intake.test.ts test/integration/release-manifest.test.ts`

Expected: PASS; the standalone verifier accepts intact blocked evidence and rejects every tampered workflow artifact.

- [ ] **Step 5: Commit bundle integration**

```bash
git add SMS/scripts/build-offline-bundle.mjs SMS/scripts/build-offline-bundle.d.mts SMS/scripts/verify-offline.mjs SMS/scripts/generate-sbom.mjs SMS/test/integration/offline-install.test.ts
git commit -m "feat(sms): bundle reviewer decision evidence"
```

### Task 7: Coordinator commands, operational documentation, and full release gate

**Files:**

- Modify: `SMS/package.json`
- Modify: `SMS/docs/release/state-aviation-acceptance-checklist.md`
- Modify: `SMS/test/integration/acceptance-review-packets.test.ts`
- Modify: `SMS/test/integration/acceptance-decision-intake.test.ts`

**Interfaces:**

- Consumes: all prior tasks.
- Produces: npm commands `acceptance:packets` and `acceptance:record`, documented coordinator steps, and final verification evidence.

- [ ] **Step 1: Write failing command and documentation assertions**

Add assertions that package scripts are exact and documentation names all safety boundaries:

```ts
expect(packageJson.scripts).toMatchObject({
  "acceptance:packets": "node scripts/generate-acceptance-review-packets.mjs",
  "acceptance:record": "node scripts/record-acceptance-decision.mjs",
});
expect(checklist).toContain("npm run acceptance:packets -- --output");
expect(checklist).toContain("npm run acceptance:record -- --packet");
expect(checklist).toContain("--apply");
expect(checklist).toContain("--recover");
expect(checklist).toContain("Every required reviewer role");
expect(checklist).toContain("does not close a known limitation");
expect(checklist).toContain("does not set `operationalReady`");
```

- [ ] **Step 2: Run command/document tests and verify RED**

Run: `cd SMS && npx vitest run test/integration/acceptance-review-packets.test.ts test/integration/acceptance-decision-intake.test.ts`

Expected: FAIL because the npm commands and coordinator instructions are absent.

- [ ] **Step 3: Add commands and exact coordinator procedure**

Add these package scripts without changing `verify:all` ordering:

```json
"acceptance:packets": "node scripts/generate-acceptance-review-packets.mjs",
"acceptance:record": "node scripts/record-acceptance-decision.mjs"
```

Add a checklist section with this command flow, using coordinator-selected exact UTC values and controlled paths:

```bash
npm run acceptance:packets -- --output dist/acceptance-reviewer-packets --as-of 2026-08-12T16:00:00.000Z
npm run acceptance:record -- --packet dist/acceptance-reviewer-packets/risk-authority/packet-manifest.json --decision /controlled/intake/risk-authority-decision.json --as-of 2026-08-12T18:00:00.000Z
npm run acceptance:record -- --packet dist/acceptance-reviewer-packets/risk-authority/packet-manifest.json --decision /controlled/intake/risk-authority-decision.json --as-of 2026-08-12T18:00:00.000Z --apply
npm run acceptance:record -- --recover --as-of 2026-08-12T18:00:00.000Z
```

State that paths and times are examples to replace, dry-run is mandatory before apply, each required role records separately, packets must be regenerated after every apply, artifacts must be unclassified and placed below the controlled artifact directory, and recording never closes a limitation or sets readiness.

- [ ] **Step 4: Run the complete verification ladder**

Run from `SMS/` in this order:

```bash
npx vitest run test/integration/acceptance-contracts.test.ts test/integration/acceptance-review-packets.test.ts test/integration/acceptance-decision-intake.test.ts test/integration/operational-readiness.test.ts test/integration/offline-install.test.ts
npm run typecheck
npm run lint
npm run verify:acceptance
npx vitest run --reporter=dot
npm run verify:all
npm run acceptance:packets -- --output dist/acceptance-reviewer-packets --as-of 2026-08-12T16:00:00.000Z
node scripts/verify-operational-readiness.mjs --require-ready
```

Expected:

- Focused tests, typecheck, lint, full Vitest, and `verify:all` PASS.
- Real packet generation reports nine packets and leaves authoritative hashes unchanged.
- Normal readiness verification PASSes structurally with nine pending scopes, ten open limitations, zero signatures, and `operationalReady=false`.
- `--require-ready` exits 1 intentionally because qualified reviews and limitation closures remain outstanding.
- If Docker is available, build a final disconnected bundle with a unique output path and verify it with `--no-network`; otherwise retain the existing intentional Docker skip and report it explicitly.

- [ ] **Step 5: Commit the coordinator workflow**

```bash
git add SMS/package.json SMS/docs/release/state-aviation-acceptance-checklist.md SMS/test/integration/acceptance-review-packets.test.ts SMS/test/integration/acceptance-decision-intake.test.ts
git commit -m "docs(sms): document institutional decision workflow"
```

### Task 8: Branch audit and publication

**Files:**

- Verify only; do not stage unrelated working-tree artifacts.

**Interfaces:**

- Consumes: all implementation commits and verification evidence.
- Produces: a clean feature diff stacked on `feat/sms-acceptance-evidence`, a pushed branch, and a draft pull request.

- [ ] **Step 1: Audit the exact diff and preserved real readiness state**

Run:

```bash
git diff --check feat/sms-acceptance-evidence...HEAD
git diff --stat feat/sms-acceptance-evidence...HEAD
git status --short --branch
node scripts/verify-operational-readiness.mjs --json
```

Expected: no whitespace errors; only intended design, plan, scripts, declarations, tests, package metadata, and checklist changes appear in the branch diff; unrelated Python bytecode, `.playwright-mcp/`, existing untracked plan files, research notes, and screenshots remain unstaged; the real ledger has zero decisions and readiness remains blocked.

- [ ] **Step 2: Push the stacked branch**

```bash
git push -u origin feat/sms-reviewer-intake
```

Expected: branch is published without changing the base branches.

- [ ] **Step 3: Open a draft stacked pull request**

Create `/tmp/sms-reviewer-intake-pr.md` with this exact content using the file-editing tool:

```markdown
## Summary

- generate deterministic, hash-locked packets for all nine institutional review scopes
- require append-only human decisions from every required role, with dry-run validation and journaled recovery
- verify current and historical reviewer evidence in the disconnected bundle

## Verification

- focused acceptance and offline integration tests
- typecheck and lint
- full Vitest suite and `verify:all`
- real packet generation leaves the signature ledger empty and readiness blocked

## Governance boundary

This pull request does not record FAC/AAAES acceptance, close any of the ten release-blocking limitations, set `operationalReady`, or begin P7 future profiles.
```

Then run:

```bash
gh pr create --draft --base feat/sms-acceptance-evidence --head feat/sms-reviewer-intake --title "feat(sms): add reviewer decision intake" --body-file /tmp/sms-reviewer-intake-pr.md
```

- [ ] **Step 4: Confirm remote checks and report the governance boundary**

Run:

```bash
gh pr checks --watch
gh pr view --json url,isDraft,mergeable,headRefName,baseRefName,commits,files,statusCheckRollup
```

Expected: required CI checks pass; the PR remains draft and stacked on `feat/sms-acceptance-evidence`. Do not begin P7 or claim operational acceptance.
