import type { SourceRecord } from "./types.js";

const SHA256 = /^[a-f0-9]{64}$/;
const hasOwn = (value: object, key: string): boolean => Object.prototype.hasOwnProperty.call(value, key);
function requiredString(record: Record<string, unknown>, key: string): boolean {
  return typeof record[key] === "string" && record[key].trim().length > 0;
}
export function isUtcTimestamp(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{3})?Z$/.exec(value);
  if (match === null) return false;

  const [, yearText, monthText, dayText, hourText, minuteText, secondText] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);
  if (month < 1 || month > 12 || hour > 23 || minute > 59 || second > 59) return false;

  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const daysInMonth = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
  return day >= 1 && day <= daysInMonth;
}

export function assertSourceRecord(record: unknown): SourceRecord {
  if (record === null || typeof record !== "object" || Array.isArray(record)) throw new Error("Source record must be an object");
  const value = record as Record<string, unknown>;
  const required = ["sourceId", "title", "authority", "canonicalUri", "localPath", "mediaType", "retrievedAtUtc", "sha256", "licenseOrRestriction"];
  if (required.some((key) => !requiredString(value, key))) throw new Error("Source record is missing a required non-empty string");
  if (!hasOwn(value, "authorityRank") || ![1, 2, 3, 4, 5, 6, 7].includes(value.authorityRank as number)) throw new Error("Source record authorityRank must be between 1 and 7");
  if (!hasOwn(value, "language") || !["es", "en", "multi"].includes(value.language as string)) throw new Error("Source record language is invalid");
  if (!hasOwn(value, "sensitivity") || value.sensitivity !== "unclassified-controlled") throw new Error("Source record sensitivity must be unclassified-controlled");
  if (!hasOwn(value, "review") || !["unreviewed", "in-review", "accepted", "superseded", "rejected"].includes(value.review as string)) throw new Error("Source record review state is invalid");
  let uri: URL;
  try { uri = new URL(value.canonicalUri as string); } catch { throw new Error("Source record canonicalUri must be a valid HTTPS URI"); }
  if (uri.protocol !== "https:") throw new Error("Source record canonicalUri must use HTTPS");
  if (!SHA256.test(value.sha256 as string)) throw new Error("Source record sha256 must be a SHA-256 hex digest");
  if (value.extractionSha256 !== undefined && (typeof value.extractionSha256 !== "string" || !SHA256.test(value.extractionSha256))) throw new Error("Source record extractionSha256 must be a SHA-256 hex digest");
  if (value.extractionPath !== undefined && !requiredString(value, "extractionPath")) throw new Error("Source record extractionPath must be non-empty");
  if (value.extractionPath !== undefined && value.extractionSha256 === undefined) throw new Error("Source record extractionPath requires extractionSha256");
  if (value.supersededBy !== undefined && (typeof value.supersededBy !== "string" || value.supersededBy.trim() === "")) throw new Error("Source record supersededBy must be non-empty");
  for (const key of ["reviewerId", "reviewSignature", "reviewedAtUtc", "validFromUtc", "validUntilUtc"]) {
    if (value[key] !== undefined && !requiredString(value, key)) throw new Error(`Source record ${key} must be non-empty`);
  }
  for (const key of ["reviewedAtUtc", "validFromUtc", "validUntilUtc"]) {
    if (value[key] !== undefined && !isUtcTimestamp(value[key])) throw new Error(`Source record ${key} must be a valid UTC timestamp`);
  }
  if (value.validFromUtc !== undefined && value.validUntilUtc !== undefined && Date.parse(value.validFromUtc as string) >= Date.parse(value.validUntilUtc as string)) throw new Error("Source record validity interval is invalid");
  return record as SourceRecord;
}
