import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { verifyOperationalReadiness } from "../../scripts/verify-operational-readiness.mjs";

const requiredReviewScopes = [
  "cybersecurity-deployment",
  "emergency-response",
  "human-factors-protocol",
  "official-geospatial-data",
  "operational-checklist",
  "racae-interpretation-translation",
  "research-separation",
  "risk-authority",
  "training-safety-promotion",
] as const;

const releaseDocumentPaths = {
  acceptanceChecklistPath: "docs/release/state-aviation-acceptance-checklist.md",
  knownLimitationsPath: "docs/release/known-limitations.md",
  verificationMatrixPath: "docs/release/verification-matrix.md",
} as const;
const packetFixture = "fixture packet\n";
const artifactFixture = `${JSON.stringify({
  schemaVersion: "1.0",
  recordType: "institutional-acceptance-artifact",
  classification: "unclassified-controlled",
  contentType: "controlled-safety-metadata",
})}\n`;
const packetSha256 = createHash("sha256").update(packetFixture).digest("hex");
const artifactSha256 = createHash("sha256").update(artifactFixture).digest("hex");
const requiredRolesByScope: Record<typeof requiredReviewScopes[number], readonly string[]> = {
  "cybersecurity-deployment": ["institutional cybersecurity reviewer", "deployment authority"],
  "emergency-response": ["ERP exercise director", "safety officer", "commander"],
  "human-factors-protocol": ["human-factors authority", "ethics or protocol authority"],
  "official-geospatial-data": ["qualified geospatial reviewer", "operational data authority"],
  "operational-checklist": ["operator", "remote pilot", "maintainer", "safety officer", "commander"],
  "racae-interpretation-translation": ["qualified FAC regulatory reviewer", "designated bilingual legal reviewer"],
  "research-separation": ["research governance reviewer", "data protection reviewer"],
  "risk-authority": ["designated risk authority", "commander"],
  "training-safety-promotion": ["training authority", "safety-promotion owner"],
};

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

async function fixture(record: unknown, signatures: readonly unknown[]): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "fac-isr-readiness-"));
  temporaryDirectories.push(root);
  await mkdir(join(root, "docs/release"), { recursive: true });
  await mkdir(join(root, "docs/release/acceptance-packets"), { recursive: true });
  await mkdir(join(root, "docs/release/acceptance-artifacts"), { recursive: true });
  await mkdir(join(root, "evidence"), { recursive: true });
  await writeFile(join(root, "docs/release/operational-readiness-record.json"), `${JSON.stringify(record, null, 2)}\n`, "utf8");
  await writeFile(join(root, "docs/release/verification-signatures.jsonl"), signatures.map((signature) => JSON.stringify(signature)).join("\n"), "utf8");
  await writeFile(join(root, "docs/release/state-aviation-acceptance-checklist.md"), "# Acceptance checklist\n", "utf8");
  await writeFile(join(root, "docs/release/known-limitations.md"), "# Known limitations\n", "utf8");
  await writeFile(join(root, "docs/release/verification-matrix.md"), "# Verification matrix\n", "utf8");
  await writeFile(join(root, "evidence/verification.txt"), "verified\n", "utf8");
  await writeFile(join(root, `docs/release/acceptance-packets/${"a".repeat(64)}.json`), packetFixture, "utf8");
  await writeFile(join(root, "docs/release/acceptance-artifacts/fixture.json"), artifactFixture, "utf8");
  return root;
}

function humanSignature(scope: typeof requiredReviewScopes[number], role: unknown = `qualified reviewer for ${scope}`): Record<string, unknown> {
  const reviewerRole = typeof role === "string" ? role : `qualified reviewer for ${scope}`;
  return {
    schemaVersion: "1.0",
    recordType: "institutional-decision",
    signatureId: `human-${scope}`,
    sourcePacketId: "a".repeat(64),
    sourcePacketPath: `docs/release/acceptance-packets/${"a".repeat(64)}.json`,
    sourcePacketSha256: packetSha256,
    supersedesSignatureId: null,
    releaseId: "fac-isr-sms@0.1.0",
    reviewer: {
      identity: `reviewer-${scope}`,
      identityType: "human",
      organizationUnit: "Colombian Aerospace Force",
      role: reviewerRole,
    },
    scope,
    decision: "accept",
    signedAtUtc: "2026-08-12T00:00:00.000Z",
    evidenceHashes: [{ path: "evidence/verification.txt", sha256: "672eb8316fec83f94119a4193f9fc552513d56a147502f8be4830e017d817831" }],
    conflicts: [],
    conditions: [],
    reviewDueAtUtc: "2099-09-12T00:00:00.000Z",
    systemOfRecordRef: "FAC-RMS:fixture-001",
    institutionalArtifact: { path: "docs/release/acceptance-artifacts/fixture.json", sha256: artifactSha256 },
  };
}

function acceptedSignatures(): Record<string, unknown>[] {
  return requiredReviewScopes.flatMap((scope) => requiredRolesByScope[scope].map((role) => ({
    ...humanSignature(scope, role),
    signatureId: `human-${scope}-${role.replaceAll(/[^a-z0-9]+/giu, "-")}`,
    reviewer: { ...(humanSignature(scope, role).reviewer as object), identity: `reviewer-${scope}-${role}` },
  })));
}

function reviewerRole(signature: Record<string, unknown>): unknown {
  const reviewer = signature.reviewer;
  return reviewer !== null && typeof reviewer === "object" ? (reviewer as { role?: unknown }).role : undefined;
}

function replaceRiskAuthorityDecision(candidate: Record<string, unknown>): Record<string, unknown>[] {
  return acceptedSignatures().map((signature) => signature.scope === "risk-authority" && reviewerRole(signature) === "designated risk authority"
    ? { ...signature, ...candidate, reviewer: { ...(signature.reviewer as object), ...(candidate.reviewer as object) } }
    : signature);
}

function acceptedRecord(signatures: readonly Record<string, unknown>[]): Record<string, unknown> {
  return {
    schemaVersion: "1.0",
    operationalReady: true,
    ...releaseDocumentPaths,
    signatureLogPath: "docs/release/verification-signatures.jsonl",
    knownLimitations: [],
    requiredReviews: requiredReviewScopes.map((scope) => ({
      scope,
      status: "accepted",
      requiredReviewerRoles: requiredRolesByScope[scope],
      signatureIds: signatures
        .filter((signature) => signature.scope === scope)
        .map((signature) => signature.signatureId),
    })),
  };
}

function knownLimitation(overrides: Readonly<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    id: "LIM-TEST-001",
    category: "aircraft-capability",
    status: "open",
    releaseBlocking: true,
    summary: "Representative hardware acceptance is pending.",
    degradedDataProcedure: "Remain in non-operational evaluation mode.",
    requiredHumanAction: "Complete and sign the receiving-hardware acceptance protocol.",
    ...overrides,
  };
}

describe("institutional operational-readiness evidence", () => {
  it("reports every absent human review as pending without claiming operational readiness", () => {
    const result = spawnSync(process.execPath, ["scripts/verify-operational-readiness.mjs", "--json"], {
      cwd: process.cwd(),
      encoding: "utf8",
    });

    expect(result.status, result.stderr).toBe(0);
    const report = JSON.parse(result.stdout) as {
      readonly ok: boolean;
      readonly operationalReady: boolean;
      readonly qualification: string;
      readonly signatureCount: number;
      readonly pendingReviewScopes: readonly string[];
      readonly blockers: readonly { readonly code: string; readonly scope?: string; readonly limitationId?: string }[];
    };
    expect(report).toMatchObject({ ok: true, operationalReady: false, qualification: "blocked", signatureCount: 0 });
    expect(new Set(report.pendingReviewScopes)).toEqual(new Set(requiredReviewScopes));
    expect(report.blockers.filter(({ code }) => code === "INSTITUTIONAL_REVIEW_PENDING")).toHaveLength(requiredReviewScopes.length);
    expect(report.blockers.filter(({ code }) => code === "KNOWN_LIMITATION_OPEN")).toHaveLength(10);
  });

  it("keeps the release gate fail-closed when operational readiness is required", () => {
    const result = spawnSync(process.execPath, ["scripts/verify-operational-readiness.mjs", "--require-ready"], {
      cwd: process.cwd(),
      encoding: "utf8",
    });

    expect(result.status).toBe(1);
    expect(result.stdout).toContain("operationalReady=false");
  });

  it("records every required limitation class and an explicit critical-data exception process", async () => {
    const record = JSON.parse(await readFile(join(process.cwd(), "docs/release/operational-readiness-record.json"), "utf8")) as {
      knownLimitations: Array<Record<string, unknown>>;
    };
    const categories = new Set(record.knownLimitations.map(({ category }) => category));

    expect(categories).toEqual(new Set([
      "aircraft-capability",
      "cybersecurity-deployment",
      "human-factors",
      "official-data-dependency",
      "performance-validation",
      "profile-boundary",
      "research-limitation",
      "telemetry-field",
      "terrain-obstacle",
      "translation-gap",
    ]));
    expect(record.knownLimitations.find(({ category }) => category === "official-data-dependency"))
      .toEqual(expect.objectContaining({
        status: "open",
        releaseBlocking: true,
        controlledExceptionProcess: expect.stringContaining("delegated authority"),
      }));
    expect(record.knownLimitations.every(({ requiredHumanAction }) => typeof requiredHumanAction === "string" && requiredHumanAction.trim() !== "")).toBe(true);
  });

  it("rejects automated identities as institutional acceptance signatures", async () => {
    const signatures = requiredReviewScopes.map((scope) => ({
      schemaVersion: "1.0",
      signatureId: `automated-${scope}`,
      reviewer: {
        identity: "fac-isr-sms-ci",
        identityType: "automation",
        organizationUnit: "FAC ISR SMS software verification",
        role: "automated verifier",
      },
      scope,
      decision: "accept",
      signedAtUtc: "2026-08-12T00:00:00.000Z",
      evidenceHashes: [{ path: "dist/reports/verification-report.json", sha256: "a".repeat(64) }],
      conflicts: [],
      conditions: [],
      reviewDueAtUtc: "2026-09-12T00:00:00.000Z",
    }));
    const root = await fixture({
      schemaVersion: "1.0",
      operationalReady: true,
      ...releaseDocumentPaths,
      signatureLogPath: "docs/release/verification-signatures.jsonl",
      requiredReviews: requiredReviewScopes.map((scope) => ({
        scope,
        status: "accepted",
        signatureIds: [`automated-${scope}`],
      })),
    }, signatures);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.violations).toContainEqual(expect.objectContaining({ code: "AUTOMATED_ACCEPTANCE_FORBIDDEN" }));
  });

  it("rejects accepted review statuses that have no linked signatures", async () => {
    const root = await fixture({
      schemaVersion: "1.0",
      operationalReady: true,
      ...releaseDocumentPaths,
      signatureLogPath: "docs/release/verification-signatures.jsonl",
      requiredReviews: requiredReviewScopes.map((scope) => ({
        scope,
        status: "accepted",
        signatureIds: [],
      })),
    }, []);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.violations.filter(({ code }) => code === "MISSING_REVIEW_SIGNATURE")).toHaveLength(requiredReviewScopes.length);
  });

  it("rejects a review that links to a nonexistent signature record", async () => {
    const root = await fixture({
      schemaVersion: "1.0",
      operationalReady: true,
      ...releaseDocumentPaths,
      signatureLogPath: "docs/release/verification-signatures.jsonl",
      requiredReviews: [{ scope: "risk-authority", status: "accepted", signatureIds: ["missing-signature"] }],
    }, []);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.violations).toContainEqual(expect.objectContaining({ code: "REVIEW_SIGNATURE_NOT_FOUND", scope: "risk-authority" }));
  });

  it("rejects readiness when any required institutional review scope is absent", async () => {
    const signature = humanSignature("risk-authority");
    const root = await fixture({
      schemaVersion: "1.0",
      operationalReady: true,
      ...releaseDocumentPaths,
      signatureLogPath: "docs/release/verification-signatures.jsonl",
      requiredReviews: [{ scope: "risk-authority", status: "accepted", signatureIds: [signature.signatureId] }],
    }, [signature]);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.violations.filter(({ code }) => code === "REQUIRED_REVIEW_SCOPE_MISSING")).toHaveLength(requiredReviewScopes.length - 1);
  });

  it("rejects duplicate institutional review scopes", async () => {
    const signatures = acceptedSignatures();
    const record = acceptedRecord(signatures);
    const root = await fixture({
      ...record,
      requiredReviews: [
        ...(record.requiredReviews as readonly unknown[]),
        { scope: "risk-authority", status: "accepted", signatureIds: ["human-risk-authority"] },
      ],
    }, signatures);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.violations).toContainEqual(expect.objectContaining({ code: "REQUIRED_REVIEW_SCOPE_DUPLICATE", scope: "risk-authority" }));
  });

  it("rejects an unrecognized institutional review status", async () => {
    const signatures = acceptedSignatures();
    const record = acceptedRecord(signatures);
    const reviews = record.requiredReviews as readonly Record<string, unknown>[];
    const root = await fixture({
      ...record,
      requiredReviews: reviews.map((review) => review.scope === "risk-authority"
        ? { ...review, status: "waived" }
        : review),
    }, signatures);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.violations).toContainEqual(expect.objectContaining({ code: "REVIEW_STATUS_INVALID", scope: "risk-authority" }));
  });

  it("rejects duplicate institutional signature identifiers", async () => {
    const signatures = acceptedSignatures();
    signatures[1] = { ...signatures[1], signatureId: signatures[0]?.signatureId };
    const root = await fixture(acceptedRecord(signatures), signatures);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.violations).toContainEqual(expect.objectContaining({ code: "SIGNATURE_ID_DUPLICATE" }));
  });

  it("rejects a readiness record without a structured limitations register", async () => {
    const signatures = acceptedSignatures();
    const { knownLimitations: _knownLimitations, ...record } = acceptedRecord(signatures);
    const root = await fixture(record, signatures);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.violations).toContainEqual(expect.objectContaining({ code: "KNOWN_LIMITATIONS_INVALID" }));
  });

  it("rejects a non-boolean operational-readiness state", async () => {
    const signatures = acceptedSignatures();
    const root = await fixture({ ...acceptedRecord(signatures), operationalReady: "true" }, signatures);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.violations).toContainEqual(expect.objectContaining({ code: "READINESS_STATE_INVALID" }));
  });

  it("rejects a release-document reference that escapes the repository", async () => {
    const signatures = acceptedSignatures();
    const root = await fixture({
      ...acceptedRecord(signatures),
      acceptanceChecklistPath: "../forged-acceptance.md",
    }, signatures);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.violations).toContainEqual(expect.objectContaining({
      code: "READINESS_DOCUMENT_INVALID",
      detail: expect.stringMatching(/traversal|relative/u),
    }));
  });

  it("rejects a signature-ledger reference that escapes the repository", async () => {
    const signatures = acceptedSignatures();
    const root = await fixture({
      ...acceptedRecord(signatures),
      signatureLogPath: "../forged-signatures.jsonl",
    }, signatures);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.violations).toContainEqual(expect.objectContaining({
      code: "SIGNATURE_LOG_INVALID",
      detail: expect.stringMatching(/traversal|relative/u),
    }));
  });

  it.each([
    ["identifier", knownLimitation({ id: "" })],
    ["category", knownLimitation({ category: "miscellaneous" })],
    ["status", knownLimitation({ status: "deferred" })],
    ["release impact", knownLimitation({ releaseBlocking: "yes" })],
    ["summary", knownLimitation({ summary: "" })],
    ["degraded-data procedure", knownLimitation({ degradedDataProcedure: "" })],
    ["required human action", knownLimitation({ requiredHumanAction: "" })],
  ] as const)("rejects a known limitation with an invalid %s", async (_name, limitation) => {
    const signatures = acceptedSignatures();
    const root = await fixture({ ...acceptedRecord(signatures), knownLimitations: [limitation] }, signatures);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.violations).toContainEqual(expect.objectContaining({ code: "KNOWN_LIMITATION_INVALID" }));
  });

  it("rejects duplicate known-limitation identifiers", async () => {
    const signatures = acceptedSignatures();
    const root = await fixture({
      ...acceptedRecord(signatures),
      knownLimitations: [knownLimitation(), knownLimitation({ summary: "A second limitation reused the identifier." })],
    }, signatures);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.violations).toContainEqual(expect.objectContaining({ code: "KNOWN_LIMITATION_ID_DUPLICATE", limitationId: "LIM-TEST-001" }));
  });

  it.each([
    ["schema version", { ...humanSignature("risk-authority"), schemaVersion: "2.0" }],
    ["signature identity", { ...humanSignature("risk-authority"), signatureId: "" }],
    ["reviewer identity", { ...humanSignature("risk-authority"), reviewer: { ...(humanSignature("risk-authority").reviewer as object), identity: "" } }],
    ["organization unit", { ...humanSignature("risk-authority"), reviewer: { ...(humanSignature("risk-authority").reviewer as object), organizationUnit: "" } }],
    ["reviewer role", { ...humanSignature("risk-authority"), reviewer: { ...(humanSignature("risk-authority").reviewer as object), role: "" } }],
    ["review scope", { ...humanSignature("risk-authority"), scope: "unapproved-scope" }],
    ["decision", { ...humanSignature("risk-authority"), decision: "observe" }],
    ["signature time", { ...humanSignature("risk-authority"), signedAtUtc: "12 August 2026" }],
    ["evidence hashes", { ...humanSignature("risk-authority"), evidenceHashes: [] }],
    ["conflict disclosure", { ...humanSignature("risk-authority"), conflicts: "none" }],
    ["conflict entry", { ...humanSignature("risk-authority"), conflicts: [1] }],
    ["acceptance conditions", { ...humanSignature("risk-authority"), conditions: "none" }],
    ["acceptance condition entry", { ...humanSignature("risk-authority"), conditions: [""] }],
    ["empty conditional acceptance", { ...humanSignature("risk-authority"), decision: "accept-with-conditions", conditions: [] }],
    ["conditions on unconditional acceptance", { ...humanSignature("risk-authority"), conditions: ["Unresolved constraint."] }],
    ["review date", { ...humanSignature("risk-authority"), reviewDueAtUtc: "2026-08-11T00:00:00.000Z" }],
  ] as const)("rejects an institutional signature with invalid %s", async (_name, candidate) => {
    const signatures = replaceRiskAuthorityDecision(candidate);
    const root = await fixture(acceptedRecord(signatures), signatures);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.violations).toContainEqual(expect.objectContaining({ code: "SIGNATURE_RECORD_INVALID" }));
  });

  it.each([
    ["mismatched hash", [{ path: "evidence/verification.txt", sha256: "b".repeat(64) }]],
    ["escaping path", [{ path: "../outside-evidence.txt", sha256: "672eb8316fec83f94119a4193f9fc552513d56a147502f8be4830e017d817831" }]],
  ] as const)("rejects signature evidence with a %s", async (_name, evidenceHashes) => {
    const candidate = { ...humanSignature("risk-authority"), evidenceHashes };
    const signatures = replaceRiskAuthorityDecision(candidate);
    const root = await fixture(acceptedRecord(signatures), signatures);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.violations).toContainEqual(expect.objectContaining({ code: "SIGNATURE_EVIDENCE_INVALID", scope: "risk-authority" }));
  });

  it.each([
    ["arbitrary plain text", "not institutional metadata\n"],
    ["classified metadata", `${JSON.stringify({
      schemaVersion: "1.0",
      recordType: "institutional-acceptance-artifact",
      classification: "classified",
      contentType: "controlled-safety-metadata",
    })}\n`],
  ] as const)("rejects an institutional artifact containing %s even when its hash matches", async (_name, contents) => {
    const sha256 = createHash("sha256").update(contents).digest("hex");
    const signatures = acceptedSignatures().map((signature) => ({
      ...signature,
      institutionalArtifact: { path: "docs/release/acceptance-artifacts/fixture.json", sha256 },
    }));
    const root = await fixture(acceptedRecord(signatures), signatures);
    await writeFile(join(root, "docs/release/acceptance-artifacts/fixture.json"), contents, "utf8");

    const report = await verifyOperationalReadiness(root);

    expect(report.violations).toContainEqual(expect.objectContaining({
      code: "SIGNATURE_EVIDENCE_INVALID",
      scope: "risk-authority",
    }));
  });

  it("rejects an institutional artifact outside the controlled acceptance-artifact directory", async () => {
    const signatures = acceptedSignatures().map((signature) => ({
      ...signature,
      institutionalArtifact: { path: "evidence/verification.txt", sha256: "672eb8316fec83f94119a4193f9fc552513d56a147502f8be4830e017d817831" },
    }));
    const root = await fixture(acceptedRecord(signatures), signatures);

    const report = await verifyOperationalReadiness(root);

    expect(report.violations).toContainEqual(expect.objectContaining({
      code: "SIGNATURE_RECORD_INVALID",
      scope: "risk-authority",
    }));
  });

  it("rejects an institutional signature after its review date", async () => {
    const signatures = acceptedSignatures();
    const root = await fixture(acceptedRecord(signatures), signatures);

    const report = await verifyOperationalReadiness(root, { asOfUtc: "2100-01-01T00:00:00.000Z" });

    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.violations.filter(({ code }) => code === "SIGNATURE_REVIEW_EXPIRED")).toHaveLength(signatures.length);
  });

  it("rejects an institutional signature dated after the verification time", async () => {
    const signatures = acceptedSignatures();
    const root = await fixture(acceptedRecord(signatures), signatures);

    const report = await verifyOperationalReadiness(root, { asOfUtc: "2026-08-11T00:00:00.000Z" });

    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.violations.filter(({ code }) => code === "SIGNATURE_TIME_INVALID")).toHaveLength(signatures.length);
  });

  it.each([
    ["different review scope", { ...humanSignature("risk-authority"), scope: "operational-checklist" }, "REVIEW_STATUS_DERIVATION_MISMATCH"],
    ["rejection decision", { ...humanSignature("risk-authority"), decision: "reject" }, "REVIEW_STATUS_DERIVATION_MISMATCH"],
  ] as const)("rejects an accepted review linked to a signature with a %s", async (_name, candidate, expectedCode) => {
    const signatures = replaceRiskAuthorityDecision(candidate);
    const root = await fixture(acceptedRecord(signatures), signatures);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.violations).toContainEqual(expect.objectContaining({ code: expectedCode, scope: "risk-authority" }));
  });

  it("keeps a structurally valid record blocked while a release-blocking limitation is open", async () => {
    const signatures = acceptedSignatures();
    const root = await fixture({
      ...acceptedRecord(signatures),
      operationalReady: false,
      knownLimitations: [knownLimitation()],
    }, signatures);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(true);
    expect(report.operationalReady).toBe(false);
    expect(report.qualification).toBe("blocked");
    expect(report.blockers).toContainEqual(expect.objectContaining({ code: "KNOWN_LIMITATION_OPEN", limitationId: "LIM-TEST-001" }));
  });

  it("keeps a structurally valid record blocked when a human review rejects its scope", async () => {
    const signatures = acceptedSignatures().map((signature) => signature.scope === "risk-authority" && reviewerRole(signature) === "designated risk authority"
      ? { ...signature, decision: "reject" }
      : signature);
    const record = acceptedRecord(signatures);
    const root = await fixture({
      ...record,
      operationalReady: false,
      requiredReviews: (record.requiredReviews as readonly Record<string, unknown>[]).map((review) => review.scope === "risk-authority"
        ? { ...review, status: "rejected" }
        : review),
    }, signatures);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(true);
    expect(report.operationalReady).toBe(false);
    expect(report.qualification).toBe("blocked");
    expect(report.blockers).toContainEqual(expect.objectContaining({ code: "INSTITUTIONAL_REVIEW_REJECTED", scope: "risk-authority" }));
  });

  it("keeps a conditional human acceptance blocked until its conditions are closed", async () => {
    const signatures = acceptedSignatures().map((signature) => signature.scope === "risk-authority" && reviewerRole(signature) === "designated risk authority"
      ? { ...signature, decision: "accept-with-conditions", conditions: ["Complete live command-post exercise."] }
      : signature);
    const record = acceptedRecord(signatures);
    const root = await fixture({
      ...record,
      operationalReady: false,
      requiredReviews: (record.requiredReviews as readonly Record<string, unknown>[]).map((review) => review.scope === "risk-authority"
        ? { ...review, status: "accepted-with-conditions" }
        : review),
    }, signatures);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(true);
    expect(report.operationalReady).toBe(false);
    expect(report.blockers).toContainEqual(expect.objectContaining({ code: "ACCEPTANCE_CONDITION_OPEN", scope: "risk-authority" }));
  });

  it("rejects an operational-readiness claim while any release blocker remains open", async () => {
    const signatures = acceptedSignatures();
    const root = await fixture({
      ...acceptedRecord(signatures),
      knownLimitations: [knownLimitation()],
    }, signatures);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(false);
    expect(report.operationalReady).toBe(false);
    expect(report.violations).toContainEqual(expect.objectContaining({ code: "READINESS_OVERCLAIMED" }));
  });

  it("keeps a review pending until every required reviewer role records an accepted head decision", async () => {
    const signatures = acceptedSignatures().filter((signature) => signature.signatureId !== "human-risk-authority-commander");
    const record = acceptedRecord(signatures);
    const root = await fixture({
      ...record,
      operationalReady: false,
      requiredReviews: (record.requiredReviews as readonly Record<string, unknown>[]).map((review) => review.scope === "risk-authority"
        ? { ...review, status: "pending", requiredReviewerRoles: requiredRolesByScope["risk-authority"] }
        : review),
    }, signatures);

    const report = await verifyOperationalReadiness(root);

    expect(report.ok).toBe(true);
    expect(report.pendingReviewScopes).toContain("risk-authority");
    expect(report.blockers).toContainEqual(expect.objectContaining({ code: "REVIEW_ROLE_MISSING", scope: "risk-authority" }));
  });

  it("rejects an append-only fork, unlinked decision, and record status that disagrees with the role heads", async () => {
    const signatures = acceptedSignatures();
    const first = signatures.find((signature) => signature.signatureId === "human-risk-authority-commander");
    const replacement = {
      ...first,
      signatureId: "cmd-replacement",
      supersedesSignatureId: "human-risk-authority-commander",
      signedAtUtc: "2026-08-12T01:00:00.000Z",
    };
    const fork = {
      ...first,
      signatureId: "cmd-fork",
      supersedesSignatureId: "human-risk-authority-commander",
      signedAtUtc: "2026-08-12T02:00:00.000Z",
    };
    const unlinked = { ...first, signatureId: "cmd-unlinked", reviewer: { ...(first?.reviewer as object), identity: "reviewer-cmd-unlinked" } };
    const root = await fixture({
      ...acceptedRecord([...signatures, replacement, fork]),
      operationalReady: false,
      requiredReviews: (acceptedRecord([...signatures, replacement, fork]).requiredReviews as readonly Record<string, unknown>[]).map((review) => review.scope === "risk-authority"
        ? { ...review, status: "accepted" }
        : review),
    }, [...signatures, replacement, fork, unlinked]);

    const report = await verifyOperationalReadiness(root);

    expect(report.violations).toEqual(expect.arrayContaining([
      expect.objectContaining({ code: "DECISION_CHAIN_FORK", scope: "risk-authority" }),
      expect.objectContaining({ code: "SIGNATURE_UNLINKED", scope: "risk-authority" }),
      expect.objectContaining({ code: "REVIEW_STATUS_DERIVATION_MISMATCH", scope: "risk-authority" }),
    ]));
  });

  it("validates source-packet and institutional-artifact hashes and rejects an active transaction journal by default", async () => {
    const signatures = acceptedSignatures();
    const root = await fixture(acceptedRecord(signatures), signatures);
    await writeFile(join(root, "docs/release/acceptance-artifacts/fixture.json"), "tampered artifact\n", "utf8");
    await writeFile(join(root, "docs/release/.acceptance-transaction.json"), "{}\n", "utf8");

    const blocked = await verifyOperationalReadiness(root);
    const allowed = await verifyOperationalReadiness(root, { allowTransactionJournal: true });

    expect(blocked.violations).toEqual(expect.arrayContaining([
      expect.objectContaining({ code: "SIGNATURE_EVIDENCE_INVALID" }),
      expect.objectContaining({ code: "ACCEPTANCE_TRANSACTION_ACTIVE" }),
    ]));
    expect(allowed.violations).not.toContainEqual(expect.objectContaining({ code: "ACCEPTANCE_TRANSACTION_ACTIVE" }));
  });
});
