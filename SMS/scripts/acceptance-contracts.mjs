import { createHash } from "node:crypto";
import { lstat, open, readFile, realpath } from "node:fs/promises";
import { isAbsolute, relative, resolve, sep } from "node:path";

const EXACT_UTC = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{3}))?Z$/u;

export const REQUIRED_REVIEW_SCOPES = Object.freeze([
  "cybersecurity-deployment", "emergency-response", "human-factors-protocol",
  "official-geospatial-data", "operational-checklist", "racae-interpretation-translation",
  "research-separation", "risk-authority", "training-safety-promotion",
]);
export const REVIEW_STATUSES = Object.freeze(["pending", "accepted", "accepted-with-conditions", "rejected"]);
export const KNOWN_LIMITATION_CATEGORIES = Object.freeze([
  "aircraft-capability",
  "terrain-obstacle",
  "official-data-dependency",
  "telemetry-field",
  "profile-boundary",
  "translation-gap",
  "research-limitation",
  "human-factors",
  "cybersecurity-deployment",
  "performance-validation",
]);
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

export function sha256Bytes(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

export async function sha256File(path) {
  const handle = await open(path, "r");
  const hash = createHash("sha256");
  try {
    for await (const chunk of handle.createReadStream({ autoClose: false })) hash.update(chunk);
    return hash.digest("hex");
  } finally {
    await handle.close();
  }
}

export function nonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}

export function exactUtc(value) {
  if (typeof value !== "string") return false;
  const match = EXACT_UTC.exec(value);
  if (match === null) return false;
  const [, year, month, day, hour, minute, second, milliseconds = "000"] = match;
  const date = new Date(value);
  return Number.isFinite(date.getTime())
    && date.getUTCFullYear() === Number(year)
    && date.getUTCMonth() + 1 === Number(month)
    && date.getUTCDate() === Number(day)
    && date.getUTCHours() === Number(hour)
    && date.getUTCMinutes() === Number(minute)
    && date.getUTCSeconds() === Number(second)
    && date.getUTCMilliseconds() === Number(milliseconds);
}

export async function readJsonLines(path) {
  const contents = await readFile(path, "utf8");
  return contents.split(/\r?\n/u).flatMap((line, index) => {
    if (line.trim() === "") return [];
    try {
      return [JSON.parse(line)];
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      throw new Error(`JSON line ${index + 1} is invalid: ${detail}`);
    }
  });
}

export async function resolveContainedExistingFile(root, candidate, label = "file") {
  if (!nonEmptyString(candidate) || isAbsolute(candidate) || candidate.includes("\\") || candidate.includes("\0")) {
    throw new Error(`${label} path must be a relative POSIX path`);
  }
  const components = candidate.split("/");
  if (components.some((component) => component === "" || component === "." || component === "..")) {
    throw new Error(`${label} path contains traversal`);
  }

  const repositoryRoot = resolve(root);
  const target = resolve(repositoryRoot, candidate);
  const fromRoot = relative(repositoryRoot, target);
  if (fromRoot === "" || fromRoot === ".." || fromRoot.startsWith(`..${sep}`) || isAbsolute(fromRoot)) {
    throw new Error(`${label} path escapes the repository root`);
  }

  let current = repositoryRoot;
  for (const component of components) {
    current = resolve(current, component);
    const stat = await lstat(current);
    if (stat.isSymbolicLink()) throw new Error(`${label} path contains a symbolic link`);
  }
  const targetStat = await lstat(target);
  if (!targetStat.isFile()) throw new Error(`${label} path must reference a regular file`);

  const [realRoot, realTarget] = await Promise.all([realpath(repositoryRoot), realpath(target)]);
  const fromRealRoot = relative(realRoot, realTarget);
  if (fromRealRoot === "" || fromRealRoot === ".." || fromRealRoot.startsWith(`..${sep}`) || isAbsolute(fromRealRoot)) {
    throw new Error(`${label} path escapes the repository root`);
  }
  return target;
}
