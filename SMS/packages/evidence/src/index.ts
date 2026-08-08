import type { SourceRecord } from "./types.js";

export { canonicalJson, sha256File } from "./hash.js";
export type {
  EvidenceId,
  EvidenceReference,
  NormalizedRequirement,
  RequirementTranslation,
  SignedPackageManifest,
  SourceId,
  SourceRecord,
} from "./types.js";

const SHA256 = /^[a-f0-9]{64}$/;
const hasOwn = (value: object, key: string): boolean =>
  Object.prototype.hasOwnProperty.call(value, key);

function requiredString(record: Record<string, unknown>, key: string): boolean {
  return typeof record[key] === "string" && record[key].trim().length > 0;
}

export function assertSourceRecord(record: unknown): SourceRecord {
  if (record === null || typeof record !== "object" || Array.isArray(record)) {
    throw new Error("Source record must be an object");
  }
  const value = record as Record<string, unknown>;
  const required = [
    "sourceId", "title", "authority", "canonicalUri", "localPath", "mediaType",
    "retrievedAtUtc", "sha256", "licenseOrRestriction",
  ];
  if (required.some((key) => !requiredString(value, key))) {
    throw new Error("Source record is missing a required non-empty string");
  }
  if (!hasOwn(value, "authorityRank") || ![1, 2, 3, 4, 5, 6, 7].includes(value.authorityRank as number)) {
    throw new Error("Source record authorityRank must be between 1 and 7");
  }
  if (!hasOwn(value, "language") || !["es", "en", "multi"].includes(value.language as string)) {
    throw new Error("Source record language is invalid");
  }
  if (!hasOwn(value, "sensitivity") || value.sensitivity !== "unclassified-controlled") {
    throw new Error("Source record sensitivity must be unclassified-controlled");
  }
  if (!hasOwn(value, "review") || !["unreviewed", "in-review", "accepted", "superseded", "rejected"].includes(value.review as string)) {
    throw new Error("Source record review state is invalid");
  }
  let uri: URL;
  try {
    uri = new URL(value.canonicalUri as string);
  } catch {
    throw new Error("Source record canonicalUri must be a valid HTTPS URI");
  }
  if (uri.protocol !== "https:") throw new Error("Source record canonicalUri must use HTTPS");
  if (!SHA256.test(value.sha256 as string)) throw new Error("Source record sha256 must be a SHA-256 hex digest");
  if (value.extractionSha256 !== undefined && (typeof value.extractionSha256 !== "string" || !SHA256.test(value.extractionSha256))) {
    throw new Error("Source record extractionSha256 must be a SHA-256 hex digest");
  }
  if (value.supersededBy !== undefined && (typeof value.supersededBy !== "string" || value.supersededBy.trim() === "")) {
    throw new Error("Source record supersededBy must be non-empty");
  }
  return record as SourceRecord;
}
