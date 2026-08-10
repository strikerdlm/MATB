import type { AggregateReview } from "./types.js";

const uses: readonly AggregateReview["permittedUses"][number][] = ["training", "interface-change", "sms-assurance"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requiredText(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") throw new TypeError(`${field} is required`);
  return value.trim();
}

function textArray(value: unknown, field: string, requireOne = true): readonly string[] {
  if (!Array.isArray(value)) throw new TypeError(`${field} must be an array`);
  const result = value.map((item, index) => requiredText(item, `${field}[${index}]`));
  if (requireOne && result.length === 0) throw new TypeError(`${field} is required`);
  if (new Set(result).size !== result.length) throw new TypeError(`${field} must not contain duplicates`);
  return result;
}

function utc(value: unknown, field: string): string {
  const text = requiredText(value, field);
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(text) || !Number.isFinite(Date.parse(text))) throw new TypeError(`${field} must be UTC`);
  return text;
}

function strictKeys(value: Record<string, unknown>, allowed: readonly string[]): void {
  const unknown = Object.keys(value).find((key) => !allowed.includes(key));
  if (unknown !== undefined) throw new TypeError(`research separation boundary rejects field: ${unknown}`);
}

function freeze<T>(value: T): T {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value as Record<string, unknown>)) freeze(child);
  }
  return value;
}

export function createAggregateReview(input: unknown): AggregateReview {
  if (!isRecord(input)) throw new TypeError("aggregate review must be an object");
  strictKeys(input, ["id", "protocolIds", "ethicsApprovalIds", "analysisScope", "minimumCellSize", "permittedUses", "findings", "limitations", "reviewerId", "approvedAtUtc"]);
  if (!Number.isInteger(input.minimumCellSize) || (input.minimumCellSize as number) < 5) throw new TypeError("minimumCellSize must be an integer of at least 5");
  const permittedUses = textArray(input.permittedUses, "permittedUses");
  if (permittedUses.some((use) => !uses.includes(use as AggregateReview["permittedUses"][number]))) throw new TypeError("permittedUses contains an unapproved use");
  const ethicsApprovalIds = input.ethicsApprovalIds === undefined ? [] : textArray(input.ethicsApprovalIds, "ethicsApprovalIds");
  const analysisScope = input.analysisScope === undefined ? undefined : requiredText(input.analysisScope, "analysisScope");
  const approvedAtUtc = input.approvedAtUtc === undefined ? undefined : utc(input.approvedAtUtc, "approvedAtUtc");
  return freeze({
    id: requiredText(input.id, "id"),
    protocolIds: textArray(input.protocolIds, "protocolIds"),
    ...(ethicsApprovalIds.length === 0 ? {} : { ethicsApprovalIds }),
    ...(analysisScope === undefined ? {} : { analysisScope }),
    minimumCellSize: input.minimumCellSize as number,
    permittedUses: permittedUses as readonly AggregateReview["permittedUses"][number][],
    findings: textArray(input.findings, "findings"),
    limitations: textArray(input.limitations, "limitations"),
    reviewerId: requiredText(input.reviewerId, "reviewerId"),
    ...(approvedAtUtc === undefined ? {} : { approvedAtUtc }),
  });
}
