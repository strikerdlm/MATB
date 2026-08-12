#!/usr/bin/env node

import { mkdir, readdir, readFile, realpath, writeFile } from "node:fs/promises";
import { basename, dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";
import {
  ACCEPTANCE_EVIDENCE_PATHS,
  ACCEPTANCE_STATE_PATHS,
  REQUIRED_REVIEW_SCOPES,
  canonicalJson,
  deriveReviewDecisionState,
  exactUtc,
  readJsonLines,
  resolveContainedExistingFile,
  sha256Bytes,
  sha256File,
} from "./acceptance-contracts.mjs";
import { verifyOperationalReadiness } from "./verify-operational-readiness.mjs";

const RECORD_PATH = "docs/release/operational-readiness-record.json";
const SCOPE_HEADINGS = Object.freeze({
  "racae-interpretation-translation": "## 1. RACAE interpretation and controlled translation",
  "operational-checklist": "## 2. Representative operational checklist validation",
  "risk-authority": "## 3. Active risk matrix and delegated authority",
  "emergency-response": "## 4. Emergency-response exercises",
  "cybersecurity-deployment": "## 5. Cybersecurity and receiving-node deployment",
  "official-geospatial-data": "## 6. Official map, terrain, obstacle, AIP, and NOTAM data",
  "human-factors-protocol": "## 7. Human-factors and usability protocol",
  "research-separation": "## 8. Research and operational data separation",
  "training-safety-promotion": "## 9. Training and safety promotion",
});

function jsonWithNewline(value) {
  return `${JSON.stringify(value, null, 2)}\n`;
}

function requireExactAsOfUtc(options) {
  if (!exactUtc(options?.asOfUtc)) throw new Error("asOfUtc must be an exact UTC timestamp");
  return options.asOfUtc;
}

function selectedScopes(scopes) {
  if (scopes === undefined) return REQUIRED_REVIEW_SCOPES;
  if (!Array.isArray(scopes) || scopes.length !== 1) throw new Error("scopes must specify exactly one approved scope");
  const [scope] = scopes;
  if (!REQUIRED_REVIEW_SCOPES.includes(scope)) throw new Error(`scope is not approved: ${String(scope)}`);
  return [scope];
}

async function hashInventory(root, paths) {
  const inventory = await Promise.all(paths.map(async (path) => ({
    path,
    sha256: await sha256File(await resolveContainedExistingFile(root, path, "acceptance evidence")),
  })));
  return inventory.sort((left, right) => left.path.localeCompare(right.path));
}

function checklistExcerpt(checklist, heading) {
  const start = checklist.indexOf(heading);
  if (start === -1) throw new Error(`acceptance checklist does not contain heading: ${heading}`);
  const following = checklist.indexOf("\n## ", start + heading.length);
  return checklist.slice(start, following === -1 ? checklist.length : following).trimEnd();
}

function isWithin(parent, candidate) {
  const fromParent = relative(parent, candidate);
  return fromParent === "" || (!isAbsolute(fromParent) && fromParent !== ".." && !fromParent.startsWith(`..${sep}`));
}

async function effectiveOutputPath(output) {
  let existing = output;
  const missingSegments = [];
  while (true) {
    try {
      return resolve(await realpath(existing), ...missingSegments);
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
      const parent = dirname(existing);
      if (parent === existing) throw error;
      missingSegments.unshift(basename(existing));
      existing = parent;
    }
  }
}

function instructions(manifest, excerpt) {
  const roles = manifest.requiredReviewerRoles.map((role) => `- ${role}`).join("\n");
  const blockers = manifest.blockers.map((blocker) => `- ${blocker.code}: ${blocker.detail}`).join("\n");
  const evidence = manifest.evidence.map(({ path, sha256 }) => `- \`${path}\` — \`${sha256}\``).join("\n");
  return [
    "# Institutional acceptance review packet",
    "",
    `Release: \`${manifest.releaseId}\``,
    `Scope: \`${manifest.scope}\``,
    `Packet ID: \`${manifest.packetId}\``,
    `As of (UTC): \`${manifest.asOfUtc}\``,
    "",
    "## Required reviewer roles",
    "",
    roles,
    "",
    "## Applicable checklist section",
    "",
    excerpt,
    "",
    "## Current release blockers",
    "",
    blockers,
    "",
    "## Evidence inventory",
    "",
    evidence,
    "",
    "## Recording instructions",
    "",
    "`decision-template.json` is an unsigned, non-recordable template. A qualified human reviewer must supply the required institutional decision fields and controlled institutional artifact before a separate recording workflow can validate or record a decision.",
    "",
  ].join("\n");
}

async function ensureOutputDirectory(output) {
  await mkdir(output, { recursive: true });
  if ((await readdir(output)).length !== 0) throw new Error("output directory must not already contain files");
}

/** Generate deterministic, unsigned institutional-review packets without mutating acceptance evidence. */
export async function generateAcceptanceReviewPackets(root, output, options) {
  const repositoryRoot = resolve(root);
  const asOfUtc = requireExactAsOfUtc(options);
  const scopes = selectedScopes(options?.scopes);
  const outputDirectory = resolve(output);
  const [releaseDirectory, effectiveOutputDirectory] = await Promise.all([
    realpath(resolve(repositoryRoot, "docs/release")),
    effectiveOutputPath(outputDirectory),
  ]);
  if (isWithin(releaseDirectory, effectiveOutputDirectory)) {
    throw new Error("output directory must not be inside docs/release");
  }
  const recordPath = await resolveContainedExistingFile(repositoryRoot, RECORD_PATH, "readiness record");
  const record = JSON.parse(await readFile(recordPath, "utf8"));
  const checklistPath = await resolveContainedExistingFile(repositoryRoot, record.acceptanceChecklistPath, "acceptance checklist");
  const checklist = await readFile(checklistPath, "utf8");
  const signatures = await readJsonLines(await resolveContainedExistingFile(repositoryRoot, record.signatureLogPath, "signature log"));
  const [evidence, acceptanceState, readiness] = await Promise.all([
    hashInventory(repositoryRoot, ACCEPTANCE_EVIDENCE_PATHS),
    hashInventory(repositoryRoot, ACCEPTANCE_STATE_PATHS),
    verifyOperationalReadiness(repositoryRoot, { asOfUtc }),
  ]);
  const acceptanceStateFingerprint = sha256Bytes(canonicalJson(acceptanceState));
  const blockers = readiness.blockers.filter((blocker) => blocker.code !== "REVIEW_ROLE_MISSING");

  await ensureOutputDirectory(outputDirectory);
  const packets = [];
  for (const scope of scopes) {
    const review = Array.isArray(record.requiredReviews)
      ? record.requiredReviews.find((candidate) => candidate?.scope === scope)
      : undefined;
    if (review === undefined) throw new Error(`readiness record does not contain required review: ${scope}`);
    const state = deriveReviewDecisionState(review, signatures);
    const roleCoverage = review.requiredReviewerRoles.map((role) => {
      const head = state.roleHeads.find((candidate) => candidate.role === role);
      return head === undefined
        ? { role, signatureId: null, decision: null }
        : { role, signatureId: head.signatureId, decision: head.decision };
    });
    const checklistHeading = SCOPE_HEADINGS[scope];
    const manifestWithoutId = {
      schemaVersion: "1.0",
      recordType: "review-packet",
      releaseId: record.releaseId,
      readinessRecordId: record.recordId,
      asOfUtc,
      scope,
      title: review.title,
      requiredReviewerRoles: review.requiredReviewerRoles,
      currentStatus: state.status,
      roleCoverage,
      checklistHeading,
      blockers,
      acceptanceStateFingerprint,
      evidence,
    };
    const manifest = {
      schemaVersion: "1.0",
      recordType: "review-packet",
      packetId: sha256Bytes(canonicalJson(manifestWithoutId)),
      releaseId: manifestWithoutId.releaseId,
      readinessRecordId: manifestWithoutId.readinessRecordId,
      asOfUtc: manifestWithoutId.asOfUtc,
      scope: manifestWithoutId.scope,
      title: manifestWithoutId.title,
      requiredReviewerRoles: manifestWithoutId.requiredReviewerRoles,
      currentStatus: manifestWithoutId.currentStatus,
      roleCoverage: manifestWithoutId.roleCoverage,
      checklistHeading: manifestWithoutId.checklistHeading,
      blockers: manifestWithoutId.blockers,
      acceptanceStateFingerprint: manifestWithoutId.acceptanceStateFingerprint,
      evidence: manifestWithoutId.evidence,
    };
    const packetJson = jsonWithNewline(manifest);
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
    const packetDirectory = resolve(outputDirectory, scope);
    await mkdir(packetDirectory, { recursive: true });
    await Promise.all([
      writeFile(resolve(packetDirectory, "packet-manifest.json"), packetJson, "utf8"),
      writeFile(resolve(packetDirectory, "review-instructions.md"), instructions(manifest, checklistExcerpt(checklist, checklistHeading)), "utf8"),
      writeFile(resolve(packetDirectory, "decision-template.json"), jsonWithNewline(template), "utf8"),
    ]);
    packets.push({ manifest, template });
  }
  return { packetCount: packets.length, packets };
}

function parseCliArguments(arguments_) {
  const options = {};
  for (let index = 0; index < arguments_.length; index += 1) {
    const argument = arguments_[index];
    if (!new Set(["--output", "--as-of", "--scope"]).has(argument)) throw new Error(`unknown argument: ${argument}`);
    const value = arguments_[index + 1];
    if (value === undefined || value.startsWith("--")) throw new Error(`${argument} requires a value`);
    if (argument === "--output") {
      if (options.output !== undefined) throw new Error("--output may be specified only once");
      options.output = value;
    } else if (argument === "--as-of") {
      if (options.asOfUtc !== undefined) throw new Error("--as-of may be specified only once");
      options.asOfUtc = value;
    } else {
      if (options.scopes !== undefined) throw new Error("--scope may be specified only once");
      options.scopes = [value];
    }
    index += 1;
  }
  if (options.output === undefined || options.asOfUtc === undefined) throw new Error("--output and --as-of are required");
  return options;
}

async function main() {
  const options = parseCliArguments(process.argv.slice(2));
  const result = await generateAcceptanceReviewPackets(process.cwd(), options.output, options);
  process.stdout.write(`PASS generated ${result.packetCount} acceptance review packet(s)\n`);
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.stack ?? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
