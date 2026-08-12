import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { appendFile, cp, lstat, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { canonicalJson } from "../../scripts/acceptance-contracts.mjs";
import { generateAcceptanceReviewPackets } from "../../scripts/generate-acceptance-review-packets.mjs";
import * as decisionRecorder from "../../scripts/record-acceptance-decision.mjs";
import {
  recordAcceptanceDecision,
  recoverAcceptanceTransaction,
  validateAcceptanceDecision,
} from "../../scripts/record-acceptance-decision.mjs";
import { verifyOperationalReadiness } from "../../scripts/verify-operational-readiness.mjs";

const temporaryDirectories: string[] = [];
const smsRoot = process.cwd();
const asOfUtc = "2026-08-12T16:00:00.000Z";
const authoritativePaths = [
  "docs/release/operational-readiness-record.json",
  "docs/release/verification-signatures.jsonl",
] as const;

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

function sha256(bytes: string | Buffer): string {
  return createHash("sha256").update(bytes).digest("hex");
}

async function temporaryRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "fac-isr-decision-intake-"));
  temporaryDirectories.push(root);
  return root;
}

async function copiedSmsRoot(): Promise<string> {
  const root = await temporaryRoot();
  await cp(join(smsRoot, "docs"), join(root, "docs"), { recursive: true });
  return root;
}

async function authoritativeHashes(root: string): Promise<readonly { readonly path: string; readonly sha256: string }[]> {
  return Promise.all(authoritativePaths.map(async (path) => ({
    path,
    sha256: sha256(await readFile(join(root, path))),
  })));
}

type Packet = {
  packetId: string;
  releaseId: string;
  scope: string;
  evidence: Array<{ path: string; sha256: string }>;
  [key: string]: unknown;
};

type Decision = {
  recordType: string;
  signatureId: string;
  sourcePacketId: string;
  sourcePacketSha256: string;
  releaseId: string;
  scope: string;
  reviewer: { identity: string; identityType: string; organizationUnit: string; role: string };
  decision: string;
  signedAtUtc: string;
  evidenceHashes: unknown[];
  conditions: string[];
  reviewDueAtUtc: string;
  systemOfRecordRef: string;
  supersedesSignatureId: string | null;
  institutionalArtifact: { path: string; sha256: string };
  [key: string]: unknown;
};

type Fixture = {
  root: string;
  packetPath: string;
  decisionPath: string;
  decision: Decision;
  packet: Packet;
  artifactPath: string;
};

type JsonSnapshot = { readonly bytes: Buffer; readonly sha256: string; readonly value: unknown };
type JsonSnapshotReader = (
  path: string,
  label: string,
  afterBytesRead?: () => void | Promise<void>,
) => Promise<JsonSnapshot>;

async function installPacket(root: string): Promise<{ path: string; packet: Packet; bytes: string }> {
  const output = await temporaryRoot();
  await generateAcceptanceReviewPackets(root, join(output, "packets"), {
    asOfUtc,
    scopes: ["risk-authority"],
  });
  const sourcePath = join(output, "packets", "risk-authority", "packet-manifest.json");
  const bytes = await readFile(sourcePath, "utf8");
  const packet = JSON.parse(bytes) as Packet;
  const path = join(root, "docs/release/acceptance-packets", `${packet.packetId}.json`);
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, bytes, "utf8");
  return { path, packet, bytes };
}

function decisionFor(packet: Packet, packetBytes: string, artifactPath: string, artifactSha256: string): Decision {
  return {
    schemaVersion: "1.0",
    recordType: "institutional-decision",
    signatureId: "risk-authority-20260812",
    sourcePacketId: packet.packetId,
    sourcePacketPath: `docs/release/acceptance-packets/${packet.packetId}.json`,
    sourcePacketSha256: sha256(packetBytes),
    supersedesSignatureId: null,
    releaseId: packet.releaseId,
    reviewer: {
      identity: "Col. Ana Reviewer",
      identityType: "human",
      organizationUnit: "FAC Safety Directorate",
      role: "designated risk authority",
    },
    scope: packet.scope,
    decision: "accept",
    signedAtUtc: "2026-08-12T15:00:00.000Z",
    evidenceHashes: packet.evidence,
    conflicts: [],
    conditions: [],
    reviewDueAtUtc: "2026-08-13T15:00:00.000Z",
    systemOfRecordRef: "FAC-ISR-DECISION-2026-08-12",
    institutionalArtifact: {
      path: artifactPath,
      sha256: artifactSha256,
    },
  };
}

async function writeDecision(fixture: Fixture): Promise<void> {
  await writeFile(fixture.decisionPath, `${JSON.stringify(fixture.decision, null, 2)}\n`, "utf8");
}

async function refreshPacketAndDecision(value: Fixture): Promise<void> {
  const installed = await installPacket(value.root);
  value.packetPath = installed.path;
  value.packet = installed.packet;
  value.decision.sourcePacketId = installed.packet.packetId;
  value.decision.sourcePacketPath = `docs/release/acceptance-packets/${installed.packet.packetId}.json`;
  value.decision.sourcePacketSha256 = sha256(installed.bytes);
  value.decision.releaseId = installed.packet.releaseId;
  value.decision.scope = installed.packet.scope;
  value.decision.evidenceHashes = installed.packet.evidence;
  await writeDecision(value);
}

async function reauthorPacket(
  value: Fixture,
  mutate: (packetWithoutId: Record<string, unknown>) => void,
): Promise<void> {
  const packetWithoutId = structuredClone(value.packet) as Record<string, unknown>;
  delete packetWithoutId.packetId;
  mutate(packetWithoutId);
  const packet = {
    ...packetWithoutId,
    packetId: sha256(canonicalJson(packetWithoutId)),
  } as Packet;
  const packetBytes = `${JSON.stringify(packet, null, 2)}\n`;
  const packetPath = join(value.root, "docs/release/acceptance-packets", `${packet.packetId}.json`);
  await writeFile(packetPath, packetBytes, "utf8");
  value.packet = packet;
  value.packetPath = packetPath;
  value.decision.sourcePacketId = packet.packetId;
  value.decision.sourcePacketPath = `docs/release/acceptance-packets/${packet.packetId}.json`;
  value.decision.sourcePacketSha256 = sha256(packetBytes);
  value.decision.releaseId = packet.releaseId;
  value.decision.scope = packet.scope;
  value.decision.evidenceHashes = packet.evidence;
  await writeDecision(value);
}

async function fixture(): Promise<Fixture> {
  const root = await copiedSmsRoot();
  const artifactPath = "docs/release/acceptance-artifacts/risk-authority-decision.json";
  const artifactBytes = `${JSON.stringify({
    schemaVersion: "1.0",
    recordType: "institutional-acceptance-artifact",
    classification: "unclassified-controlled",
    contentType: "controlled-safety-metadata",
  }, null, 2)}\n`;
  const absoluteArtifactPath = join(root, artifactPath);
  await mkdir(dirname(absoluteArtifactPath), { recursive: true });
  await writeFile(absoluteArtifactPath, artifactBytes, "utf8");
  const installed = await installPacket(root);
  const decision = decisionFor(installed.packet, installed.bytes, artifactPath, sha256(artifactBytes));
  const decisionPath = join(root, "candidate-decision.json");
  const result = { root, packetPath: installed.path, decisionPath, decision, packet: installed.packet, artifactPath: absoluteArtifactPath };
  await writeDecision(result);
  return result;
}

async function addCurrentRoleHead(value: Fixture): Promise<void> {
  const prior = { ...value.decision, signatureId: "prior-risk-authority", signedAtUtc: "2026-08-12T14:00:00.000Z" };
  await appendFile(join(value.root, "docs/release/verification-signatures.jsonl"), `${JSON.stringify(prior)}\n`, "utf8");
  const recordPath = join(value.root, "docs/release/operational-readiness-record.json");
  const record = JSON.parse(await readFile(recordPath, "utf8"));
  const review = record.requiredReviews.find((candidate: { scope: string }) => candidate.scope === "risk-authority");
  review.signatureIds = [prior.signatureId];
  await writeFile(recordPath, `${JSON.stringify(record, null, 2)}\n`, "utf8");
  const installed = await installPacket(value.root);
  value.packetPath = installed.path;
  value.packet = installed.packet;
  value.decision = decisionFor(installed.packet, installed.bytes, "docs/release/acceptance-artifacts/risk-authority-decision.json", sha256(await readFile(value.artifactPath)));
}

describe("institutional acceptance decision intake", () => {
  it("documents the coordinator decision workflow and its safety boundaries", async () => {
    const checklist = await readFile(join(smsRoot, "docs/release/state-aviation-acceptance-checklist.md"), "utf8");

    expect(checklist).toContain("npm run acceptance:packets -- --output");
    expect(checklist).toContain("npm run acceptance:record -- --packet");
    expect(checklist).toContain("--apply");
    expect(checklist).toContain("--recover");
    expect(checklist).toContain("Every required reviewer role");
    expect(checklist).toContain("does not close a known limitation");
    expect(checklist).toContain("does not set `operationalReady`");
    expect(checklist).toContain("Every generation or regeneration must use a new empty output directory");
    expect(checklist.match(/dist\/acceptance-reviewer-packets\/2026-08-12T160000000Z/gu)).toHaveLength(3);
  });

  it("applies one decision while changing only the ledger and matching review state", async () => {
    const value = await fixture();
    const recordPath = join(value.root, authoritativePaths[0]);
    const ledgerPath = join(value.root, authoritativePaths[1]);
    const beforeRecord = JSON.parse(await readFile(recordPath, "utf8"));

    const result = await recordAcceptanceDecision(value.root, value.packetPath, value.decisionPath, {
      asOfUtc,
      apply: true,
    });
    const afterRecord = JSON.parse(await readFile(recordPath, "utf8"));

    expect(result).toMatchObject({ ok: true, mode: "applied", projectedStatus: "pending" });
    expect(result.transactionId).toMatch(/^[a-f0-9]{64}$/u);
    expect(afterRecord.requiredReviews.find(({ scope }: { scope: string }) => scope === "risk-authority").signatureIds)
      .toEqual(["risk-authority-20260812"]);
    for (const field of ["knownLimitations", "operationalReady", "qualification", "recordStatus", "readinessDecision"] as const) {
      expect(afterRecord[field]).toEqual(beforeRecord[field]);
    }
    expect((await readFile(ledgerPath, "utf8")).trim().split("\n")).toHaveLength(1);
    await expect(lstat(join(value.root, "docs/release/.acceptance-transaction.json"))).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("derives accepted only after applying the final required role decision", async () => {
    const value = await fixture();

    const first = await recordAcceptanceDecision(value.root, value.packetPath, value.decisionPath, { asOfUtc, apply: true });
    expect(first.projectedStatus).toBe("pending");

    await refreshPacketAndDecision(value);
    value.decision.signatureId = "risk-commander-20260812";
    value.decision.reviewer.role = "commander";
    value.decision.signedAtUtc = "2026-08-12T15:30:00.000Z";
    await writeDecision(value);
    const second = await recordAcceptanceDecision(value.root, value.packetPath, value.decisionPath, { asOfUtc, apply: true });

    expect(second.projectedStatus).toBe("accepted");
    const record = JSON.parse(await readFile(join(value.root, authoritativePaths[0]), "utf8"));
    expect(record.requiredReviews.find(({ scope }: { scope: string }) => scope === "risk-authority")).toMatchObject({
      status: "accepted",
      signatureIds: ["risk-authority-20260812", "risk-commander-20260812"],
    });
  });

  it("appends a superseding role decision without deleting its predecessor", async () => {
    const value = await fixture();
    await recordAcceptanceDecision(value.root, value.packetPath, value.decisionPath, { asOfUtc, apply: true });

    await refreshPacketAndDecision(value);
    value.decision.signatureId = "risk-authority-20260812-revised";
    value.decision.supersedesSignatureId = "risk-authority-20260812";
    value.decision.signedAtUtc = "2026-08-12T15:30:00.000Z";
    await writeDecision(value);
    await recordAcceptanceDecision(value.root, value.packetPath, value.decisionPath, { asOfUtc, apply: true });

    const lines = (await readFile(join(value.root, authoritativePaths[1]), "utf8")).trim().split("\n").map((line) => JSON.parse(line));
    expect(lines.map(({ signatureId }) => signatureId)).toEqual([
      "risk-authority-20260812",
      "risk-authority-20260812-revised",
    ]);
    const record = JSON.parse(await readFile(join(value.root, authoritativePaths[0]), "utf8"));
    expect(record.requiredReviews.find(({ scope }: { scope: string }) => scope === "risk-authority").signatureIds)
      .toEqual(["risk-authority-20260812", "risk-authority-20260812-revised"]);
  });

  it("fails closed when another acceptance update owns the lock", async () => {
    const value = await fixture();
    const lockPath = join(value.root, "docs/release/.acceptance-update.lock");
    await writeFile(lockPath, "another-transaction\n", { encoding: "utf8", mode: 0o600 });
    const before = await authoritativeHashes(value.root);

    await expect(recordAcceptanceDecision(value.root, value.packetPath, value.decisionPath, { asOfUtc, apply: true }))
      .rejects.toThrow(/lock|active/u);

    expect(await authoritativeHashes(value.root)).toEqual(before);
    expect(await readFile(lockPath, "utf8")).toBe("another-transaction\n");
  });

  it("preserves a mixed crash state for explicit rollback recovery", async () => {
    const value = await fixture();
    const before = await authoritativeHashes(value.root);

    await expect(recordAcceptanceDecision(value.root, value.packetPath, value.decisionPath, {
      asOfUtc,
      apply: true,
      failpoint: "after-ledger-replace",
    })).rejects.toThrow(/failpoint/u);

    const journalPath = join(value.root, "docs/release/.acceptance-transaction.json");
    expect((await lstat(journalPath)).isFile()).toBe(true);
    const journal = JSON.parse(await readFile(journalPath, "utf8"));
    expect(journal).toMatchObject({
      schemaVersion: "1.0",
      ledger: {
        path: "docs/release/verification-signatures.jsonl",
        originalPath: `docs/release/.acceptance-transactions/${journal.transactionId}/ledger.original`,
        candidatePath: `docs/release/.acceptance-transactions/${journal.transactionId}/ledger.candidate`,
      },
      record: {
        path: "docs/release/operational-readiness-record.json",
        originalPath: `docs/release/.acceptance-transactions/${journal.transactionId}/record.original`,
        candidatePath: `docs/release/.acceptance-transactions/${journal.transactionId}/record.candidate`,
      },
    });
    expect(journal.transactionId).toBe(sha256(
      `{"candidateLedgerSha256":"${journal.ledger.candidateSha256}","candidateRecordSha256":"${journal.record.candidateSha256}","candidateSignatureId":"risk-authority-20260812"}`,
    ));
    for (const path of [journal.ledger.originalPath, journal.ledger.candidatePath, journal.record.originalPath, journal.record.candidatePath]) {
      expect((await lstat(join(value.root, path))).isFile()).toBe(true);
    }
    const record = JSON.parse(await readFile(join(value.root, authoritativePaths[0]), "utf8"));
    expect(record.operationalReady).toBe(false);
    const verification = await verifyOperationalReadiness(value.root, { asOfUtc });
    expect(verification.violations).toContainEqual(expect.objectContaining({ code: "ACCEPTANCE_TRANSACTION_INCOMPLETE" }));

    const recovery = await recoverAcceptanceTransaction(value.root, { asOfUtc });
    expect(recovery).toMatchObject({ ok: true, action: "rolled-back" });
    expect(await authoritativeHashes(value.root)).toEqual(before);
  });

  it("retries mixed-state recovery when an exact rollback stage survived interruption", async () => {
    const value = await fixture();
    const before = await authoritativeHashes(value.root);
    await expect(recordAcceptanceDecision(value.root, value.packetPath, value.decisionPath, {
      asOfUtc,
      apply: true,
      failpoint: "after-ledger-replace",
    })).rejects.toThrow(/failpoint/u);
    const journal = JSON.parse(await readFile(join(value.root, "docs/release/.acceptance-transaction.json"), "utf8"));
    const survivingStage = join(
      value.root,
      `docs/release/.acceptance-${journal.transactionId}-ledger-rollback`,
    );
    await writeFile(survivingStage, await readFile(join(value.root, journal.ledger.originalPath)));

    const recovery = await recoverAcceptanceTransaction(value.root, { asOfUtc });

    expect(recovery).toMatchObject({ ok: true, action: "rolled-back" });
    expect(await authoritativeHashes(value.root)).toEqual(before);
    await expect(lstat(survivingStage)).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("leaves a journal that explicit recovery can reacquire after durable lock removal", async () => {
    const value = await fixture();
    await expect(recordAcceptanceDecision(value.root, value.packetPath, value.decisionPath, {
      asOfUtc,
      apply: true,
      failpoint: "after-record-replace",
    })).rejects.toThrow(/failpoint/u);
    const journalPath = join(value.root, "docs/release/.acceptance-transaction.json");

    await expect(recoverAcceptanceTransaction(value.root, {
      asOfUtc,
      failpoint: "after-lock-remove",
    })).rejects.toThrow(/after-lock-remove/u);

    expect((await lstat(journalPath)).isFile()).toBe(true);
    await expect(lstat(join(value.root, "docs/release/.acceptance-update.lock"))).rejects.toMatchObject({ code: "ENOENT" });
    const verification = await verifyOperationalReadiness(value.root, { asOfUtc });
    expect(verification.violations).toContainEqual(expect.objectContaining({ code: "ACCEPTANCE_TRANSACTION_INCOMPLETE" }));
    await expect(recoverAcceptanceTransaction(value.root, { asOfUtc })).resolves.toMatchObject({
      ok: true,
      action: "finalized",
    });
    await expect(lstat(journalPath)).rejects.toMatchObject({ code: "ENOENT" });
    await expect(lstat(join(value.root, "docs/release/.acceptance-update.lock"))).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("does not leave a blocking lock after the durable journal commit point", async () => {
    const value = await fixture();
    await expect(recordAcceptanceDecision(value.root, value.packetPath, value.decisionPath, {
      asOfUtc,
      apply: true,
      failpoint: "after-record-replace",
    })).rejects.toThrow(/failpoint/u);
    const journalPath = join(value.root, "docs/release/.acceptance-transaction.json");
    const journal = JSON.parse(await readFile(journalPath, "utf8"));
    const transactionPath = join(value.root, "docs/release/.acceptance-transactions", journal.transactionId);

    await expect(recoverAcceptanceTransaction(value.root, {
      asOfUtc,
      failpoint: "after-journal-remove",
    })).rejects.toThrow(/after-journal-remove/u);

    await expect(lstat(journalPath)).rejects.toMatchObject({ code: "ENOENT" });
    expect((await lstat(transactionPath)).isDirectory()).toBe(true);
    await expect(lstat(join(value.root, "docs/release/.acceptance-update.lock"))).rejects.toMatchObject({ code: "ENOENT" });
    const verification = await verifyOperationalReadiness(value.root, { asOfUtc });
    expect(verification.violations).not.toContainEqual(expect.objectContaining({ code: "ACCEPTANCE_TRANSACTION_INCOMPLETE" }));
    await refreshPacketAndDecision(value);
    value.decision.signatureId = "risk-commander-after-cleanup-interruption";
    value.decision.reviewer.role = "commander";
    await writeDecision(value);
    await expect(recordAcceptanceDecision(value.root, value.packetPath, value.decisionPath, { asOfUtc, apply: true }))
      .resolves.toMatchObject({ ok: true, mode: "applied", projectedStatus: "accepted" });
  });

  it("refuses a corrupted original snapshot without changing authoritative mixed state", async () => {
    const value = await fixture();
    await expect(recordAcceptanceDecision(value.root, value.packetPath, value.decisionPath, {
      asOfUtc,
      apply: true,
      failpoint: "after-ledger-replace",
    })).rejects.toThrow(/failpoint/u);
    const journalPath = join(value.root, "docs/release/.acceptance-transaction.json");
    const journal = JSON.parse(await readFile(journalPath, "utf8"));
    const corruptSnapshotPath = join(value.root, journal.ledger.originalPath);
    await writeFile(corruptSnapshotPath, "corrupted rollback evidence\n", "utf8");
    const mixed = await authoritativeHashes(value.root);

    await expect(recoverAcceptanceTransaction(value.root, { asOfUtc }))
      .rejects.toThrow(/snapshot|hash|manual investigation/u);

    expect(await authoritativeHashes(value.root)).toEqual(mixed);
    expect((await lstat(journalPath)).isFile()).toBe(true);
    expect(await readFile(corruptSnapshotPath, "utf8")).toBe("corrupted rollback evidence\n");
  });

  it("finalizes recovery when both authoritative files have candidate hashes", async () => {
    const value = await fixture();

    await expect(recordAcceptanceDecision(value.root, value.packetPath, value.decisionPath, {
      asOfUtc,
      apply: true,
      failpoint: "after-record-replace",
    })).rejects.toThrow(/failpoint/u);
    const candidate = await authoritativeHashes(value.root);

    const recovery = await recoverAcceptanceTransaction(value.root, { asOfUtc });

    expect(recovery).toMatchObject({ ok: true, action: "finalized" });
    expect(await authoritativeHashes(value.root)).toEqual(candidate);
    await expect(lstat(join(value.root, "docs/release/.acceptance-transaction.json"))).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("cleans recovery metadata when both authoritative files retain original hashes", async () => {
    const value = await fixture();
    const before = await authoritativeHashes(value.root);

    await expect(recordAcceptanceDecision(value.root, value.packetPath, value.decisionPath, {
      asOfUtc,
      apply: true,
      failpoint: "after-packet-install",
    })).rejects.toThrow(/failpoint/u);

    const recovery = await recoverAcceptanceTransaction(value.root, { asOfUtc });
    expect(recovery).toMatchObject({ ok: true, action: "cleaned-original" });
    expect(await authoritativeHashes(value.root)).toEqual(before);
  });

  it("refuses recovery when an authoritative hash is neither original nor candidate", async () => {
    const value = await fixture();
    await expect(recordAcceptanceDecision(value.root, value.packetPath, value.decisionPath, {
      asOfUtc,
      apply: true,
      failpoint: "after-ledger-replace",
    })).rejects.toThrow(/failpoint/u);
    await writeFile(join(value.root, authoritativePaths[0]), "{}\n", "utf8");

    await expect(recoverAcceptanceTransaction(value.root, { asOfUtc })).rejects.toThrow(/unrecognized|manual investigation/u);

    expect((await lstat(join(value.root, "docs/release/.acceptance-transaction.json"))).isFile()).toBe(true);
  });

  it("recovers from the CLI without packet or decision arguments", async () => {
    const value = await fixture();
    const before = await authoritativeHashes(value.root);
    await expect(recordAcceptanceDecision(value.root, value.packetPath, value.decisionPath, {
      asOfUtc,
      apply: true,
      failpoint: "after-ledger-replace",
    })).rejects.toThrow(/failpoint/u);

    const result = spawnSync(process.execPath, [
      join(smsRoot, "scripts/record-acceptance-decision.mjs"),
      "--recover",
      "--as-of",
      asOfUtc,
      "--json",
    ], { cwd: value.root, encoding: "utf8" });

    expect(result.status, result.stderr).toBe(0);
    expect(JSON.parse(result.stdout)).toMatchObject({ ok: true, action: "rolled-back" });
    expect(await authoritativeHashes(value.root)).toEqual(before);
  });

  it("rejects mutually exclusive apply and recovery CLI modes", async () => {
    const value = await fixture();

    const result = spawnSync(process.execPath, [
      join(smsRoot, "scripts/record-acceptance-decision.mjs"),
      "--recover",
      "--apply",
      "--as-of",
      asOfUtc,
    ], { cwd: value.root, encoding: "utf8" });

    expect(result.status).toBe(2);
    expect(result.stderr).toMatch(/mutually exclusive/u);
  });

  it("validates an exact qualified human decision in dry-run without changing authoritative acceptance evidence", async () => {
    const value = await fixture();
    const before = await authoritativeHashes(value.root);

    const report = await validateAcceptanceDecision(value.root, value.packetPath, value.decisionPath, { asOfUtc });

    expect(report).toMatchObject({
      ok: true,
      mode: "dry-run",
      scope: "risk-authority",
      requiredRole: "designated risk authority",
      projectedStatus: "pending",
    });
    expect(await authoritativeHashes(value.root)).toEqual(before);
  });

  it.each([
    {
      name: "an incomplete evidence source set",
      mutate: (packet: Record<string, unknown>) => {
        packet.evidence = (packet.evidence as unknown[]).slice(1);
      },
    },
    {
      name: "re-authored generator-owned checklist and blocker content",
      mutate: (packet: Record<string, unknown>) => {
        packet.checklistHeading = "## Invented acceptance checklist section";
        packet.blockers = [];
      },
    },
  ])("rejects a self-consistent packet with $name before it can enter the ledger", async ({ mutate }) => {
    const value = await fixture();
    await reauthorPacket(value, mutate);
    const before = await authoritativeHashes(value.root);

    await expect(validateAcceptanceDecision(value.root, value.packetPath, value.decisionPath, { asOfUtc }))
      .rejects.toThrow(/canonical|generator|packet/u);
    await expect(recordAcceptanceDecision(value.root, value.packetPath, value.decisionPath, { asOfUtc, apply: true }))
      .rejects.toThrow(/canonical|generator|packet/u);

    expect(await authoritativeHashes(value.root)).toEqual(before);
    expect((await readFile(join(value.root, authoritativePaths[1]), "utf8")).trim()).toBe("");
    await expect(lstat(join(value.root, "docs/release/.acceptance-transaction.json"))).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("projects a valid human rejection without changing authoritative acceptance evidence", async () => {
    const value = await fixture();
    value.decision.decision = "reject";
    await writeDecision(value);
    const before = await authoritativeHashes(value.root);

    const report = await validateAcceptanceDecision(value.root, value.packetPath, value.decisionPath, { asOfUtc });

    expect(report.projectedStatus).toBe("rejected");
    expect(await authoritativeHashes(value.root)).toEqual(before);
  });

  it("projects the final required human role as accepted without changing authoritative acceptance evidence", async () => {
    const value = await fixture();
    await addCurrentRoleHead(value);
    value.decision.signatureId = "commander-20260812";
    value.decision.reviewer.role = "commander";
    await writeDecision(value);
    const before = await authoritativeHashes(value.root);

    const report = await validateAcceptanceDecision(value.root, value.packetPath, value.decisionPath, { asOfUtc });

    expect(report.projectedStatus).toBe("accepted");
    expect(await authoritativeHashes(value.root)).toEqual(before);
  });

  it.each(["packet", "artifact"])("uses one byte snapshot when a %s file changes after its handle reads", async (kind) => {
    const path = join(await temporaryRoot(), `${kind}.json`);
    const original = '{"revision":"original"}\n';
    const replacement = '{"revision":"replacement"}\n';
    await writeFile(path, original, "utf8");
    const snapshotReader = (decisionRecorder as { readRegularJsonSnapshot?: JsonSnapshotReader }).readRegularJsonSnapshot;

    expect(snapshotReader).toBeTypeOf("function");
    const snapshot = await snapshotReader!(path, `${kind} input`, async () => writeFile(path, replacement, "utf8"));

    expect(snapshot.value).toEqual({ revision: "original" });
    expect(snapshot.sha256).toBe(sha256(original));
    expect(snapshot.bytes.toString("utf8")).toBe(original);
    expect(await readFile(path, "utf8")).toBe(replacement);
  });

  it.each([
    ["unsigned template", async (value: Fixture) => { value.decision.recordType = "unsigned-decision-template"; }],
    ["automation identity", async (value: Fixture) => { value.decision.reviewer.identityType = "automation"; }],
    ["unknown role", async (value: Fixture) => { value.decision.reviewer.role = "unrecognized reviewer"; }],
    ["release mismatch", async (value: Fixture) => { value.decision.releaseId = "different-release"; }],
    ["scope mismatch", async (value: Fixture) => { value.decision.scope = "emergency-response"; }],
    ["packet identifier mismatch", async (value: Fixture) => { value.decision.sourcePacketId = "a".repeat(64); }],
    ["packet hash mismatch", async (value: Fixture) => { value.decision.sourcePacketSha256 = "b".repeat(64); }],
    ["changed acceptance-state fingerprint", async (value: Fixture) => {
      const path = join(value.root, "docs/release/operational-readiness-record.json");
      await writeFile(path, `${await readFile(path, "utf8")}\n`, "utf8");
    }],
    ["changed evidence list", async (value: Fixture) => { value.decision.evidenceHashes = [...value.decision.evidenceHashes].reverse(); }],
    ["duplicate signature identifier", async (value: Fixture) => {
      await appendFile(join(value.root, "docs/release/verification-signatures.jsonl"), `${JSON.stringify({ signatureId: value.decision.signatureId })}\n`, "utf8");
    }],
    ["malformed system-of-record reference", async (value: Fixture) => { value.decision.systemOfRecordRef = "bad\u0001reference"; }],
    ["future signing time", async (value: Fixture) => { value.decision.signedAtUtc = "2026-08-12T16:00:00.001Z"; }],
    ["expired review time", async (value: Fixture) => { value.decision.reviewDueAtUtc = asOfUtc; }],
    ["conditional decision without conditions", async (value: Fixture) => { value.decision.decision = "accept-with-conditions"; }],
    ["unconditional decision with conditions", async (value: Fixture) => { value.decision.conditions = ["perform follow-up review"]; }],
    ["artifact outside the allowed directory", async (value: Fixture) => {
      const outside = join(value.root, "outside-artifact.json");
      await writeFile(outside, await readFile(value.artifactPath));
      value.decision.institutionalArtifact.path = "outside-artifact.json";
      value.decision.institutionalArtifact.sha256 = sha256(await readFile(outside));
    }],
    ["symlink artifact", async (value: Fixture) => {
      const target = join(value.root, "artifact-target.json");
      const link = join(value.root, "docs/release/acceptance-artifacts/linked.json");
      await writeFile(target, await readFile(value.artifactPath));
      await symlink(target, link);
      value.decision.institutionalArtifact.path = "docs/release/acceptance-artifacts/linked.json";
      value.decision.institutionalArtifact.sha256 = sha256(await readFile(target));
    }],
    ["missing artifact", async (value: Fixture) => { value.decision.institutionalArtifact.path = "docs/release/acceptance-artifacts/missing.json"; }],
    ["artifact hash mismatch", async (value: Fixture) => { value.decision.institutionalArtifact.sha256 = "c".repeat(64); }],
    ["existing role head without exact supersession", async (value: Fixture) => { await addCurrentRoleHead(value); }],
    ["incorrect supersession head", async (value: Fixture) => {
      await addCurrentRoleHead(value);
      value.decision.supersedesSignatureId = "not-the-current-head";
    }],
  ])("rejects %s without changing authoritative acceptance evidence", async (_label, mutate) => {
    const value = await fixture();
    await mutate(value);
    await writeDecision(value);
    const before = await authoritativeHashes(value.root);

    await expect(validateAcceptanceDecision(value.root, value.packetPath, value.decisionPath, { asOfUtc })).rejects.toThrow();

    expect(await authoritativeHashes(value.root)).toEqual(before);
  });

  it("rejects a symbolic-link packet and decision input", async () => {
    const value = await fixture();
    const packetLink = join(value.root, "packet-link.json");
    await symlink(value.packetPath, packetLink);
    const before = await authoritativeHashes(value.root);

    await expect(validateAcceptanceDecision(value.root, packetLink, value.decisionPath, { asOfUtc })).rejects.toThrow(/symbolic link/u);
    expect((await lstat(packetLink)).isSymbolicLink()).toBe(true);
    expect(await authoritativeHashes(value.root)).toEqual(before);
  });
});
