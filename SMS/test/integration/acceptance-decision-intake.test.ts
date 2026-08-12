import { createHash } from "node:crypto";
import { appendFile, cp, lstat, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { generateAcceptanceReviewPackets } from "../../scripts/generate-acceptance-review-packets.mjs";
import * as decisionRecorder from "../../scripts/record-acceptance-decision.mjs";
import { validateAcceptanceDecision } from "../../scripts/record-acceptance-decision.mjs";

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
  readonly packetId: string;
  readonly releaseId: string;
  readonly scope: string;
  readonly evidence: unknown[];
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
