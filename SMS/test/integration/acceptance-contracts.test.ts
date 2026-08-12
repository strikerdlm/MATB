import { createHash } from "node:crypto";
import { mkdir, mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  canonicalJson,
  exactUtc,
  deriveReviewDecisionState,
  resolveContainedExistingFile,
  sha256Bytes,
} from "../../scripts/acceptance-contracts.mjs";

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

function reviewWith(signatureIds: readonly string[], overrides: Record<string, unknown> = {}) {
  return {
    scope: "risk-authority",
    status: "pending",
    requiredReviewerRoles: ["designated risk authority", "commander"],
    signatureIds,
    ...overrides,
  };
}

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

  describe("required reviewer decision chains", () => {
    it("keeps a multi-role scope pending until every required role accepts", () => {
      const state = deriveReviewDecisionState(
        reviewWith(["risk-1"]),
        [decision("risk-authority", "designated risk authority", "risk-1")],
      );

      expect(state).toMatchObject({ status: "pending", missingRoles: ["commander"] });
    });

    it("derives rejection immediately and rejects a forked supersession chain", () => {
      const first = decision("risk-authority", "commander", "cmd-1");
      const rejection = decision("risk-authority", "commander", "cmd-2", {
        decision: "reject", supersedesSignatureId: "cmd-1", signedAtUtc: "2026-08-12T16:00:00.000Z",
      });
      expect(deriveReviewDecisionState(reviewWith(["cmd-1", "cmd-2"]), [first, rejection]).status).toBe("rejected");

      const fork = decision("risk-authority", "commander", "cmd-3", {
        supersedesSignatureId: "cmd-1", signedAtUtc: "2026-08-12T17:00:00.000Z",
      });
      expect(deriveReviewDecisionState(reviewWith(["cmd-1", "cmd-2", "cmd-3"]), [first, rejection, fork]).violations)
        .toContainEqual(expect.objectContaining({ code: "DECISION_CHAIN_FORK" }));
    });

    it("accepts only when every required role has an unconditional head decision", () => {
      const risk = decision("risk-authority", "designated risk authority", "risk-1");
      const commander = decision("risk-authority", "commander", "cmd-1");
      expect(deriveReviewDecisionState(reviewWith(["risk-1", "cmd-1"]), [risk, commander]))
        .toMatchObject({ status: "accepted", missingRoles: [], roleHeads: expect.arrayContaining([
          expect.objectContaining({ role: "designated risk authority", decision: "accept" }),
          expect.objectContaining({ role: "commander", decision: "accept" }),
        ]) });
    });

    it("gives conditional heads precedence over unconditional acceptance", () => {
      const risk = decision("risk-authority", "designated risk authority", "risk-1", {
        decision: "accept-with-conditions", conditions: ["Complete exercise."],
      });
      const commander = decision("risk-authority", "commander", "cmd-1");
      expect(deriveReviewDecisionState(reviewWith(["risk-1", "cmd-1"]), [risk, commander]).status)
        .toBe("accepted-with-conditions");
    });

    it.each([
      ["cycle", [
        decision("risk-authority", "commander", "cmd-1", { supersedesSignatureId: "cmd-2", signedAtUtc: "2026-08-12T16:00:00.000Z" }),
        decision("risk-authority", "commander", "cmd-2", { supersedesSignatureId: "cmd-1", signedAtUtc: "2026-08-12T17:00:00.000Z" }),
      ], "DECISION_CHAIN_CYCLE"],
      ["skipped head", [
        decision("risk-authority", "commander", "cmd-1"),
        decision("risk-authority", "commander", "cmd-2", { supersedesSignatureId: "cmd-1", signedAtUtc: "2026-08-12T16:00:00.000Z" }),
        decision("risk-authority", "commander", "cmd-3", { supersedesSignatureId: "cmd-1", signedAtUtc: "2026-08-12T17:00:00.000Z" }),
      ], "DECISION_CHAIN_FORK"],
      ["cross-role supersession", [
        decision("risk-authority", "designated risk authority", "risk-1"),
        decision("risk-authority", "commander", "cmd-1", { supersedesSignatureId: "risk-1", signedAtUtc: "2026-08-12T16:00:00.000Z" }),
      ], "DECISION_CHAIN_ROLE_MISMATCH"],
      ["cross-scope supersession", [
        decision("operational-checklist", "commander", "ops-1"),
        decision("risk-authority", "commander", "cmd-1", { supersedesSignatureId: "ops-1", signedAtUtc: "2026-08-12T16:00:00.000Z" }),
      ], "DECISION_CHAIN_SCOPE_MISMATCH"],
    ] as const)("rejects %s history", (_name, decisions, code) => {
      expect(deriveReviewDecisionState(reviewWith(decisions.map(({ signatureId }) => signatureId)), decisions).violations)
        .toContainEqual(expect.objectContaining({ code }));
    });

    it("rejects an unlinked decision, unknown required role, and mismatched record status", () => {
      const accepted = decision("risk-authority", "designated risk authority", "risk-1");
      const unlinked = decision("risk-authority", "commander", "cmd-1");
      expect(deriveReviewDecisionState(reviewWith(["risk-1"]), [accepted, unlinked]).violations)
        .toContainEqual(expect.objectContaining({ code: "SIGNATURE_UNLINKED" }));
      expect(deriveReviewDecisionState(
        reviewWith(["risk-1"], { requiredReviewerRoles: ["unknown authority"] }),
        [accepted],
      ).violations).toContainEqual(expect.objectContaining({ code: "REVIEW_ROLE_UNKNOWN" }));
      expect(deriveReviewDecisionState(reviewWith(["risk-1"], { status: "accepted" }), [accepted]).violations)
        .toContainEqual(expect.objectContaining({ code: "REVIEW_STATUS_DERIVATION_MISMATCH" }));
    });
  });
});
