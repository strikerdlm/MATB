import type { CorrectiveAction } from "./types.js";

export interface VerificationResult { readonly status: "verified" | "ineffective" | "blocked"; readonly evidenceRefs: readonly string[]; readonly reviewerId?: string }
export interface VerificationInput { readonly reviewerId: string; readonly evidenceRefs: readonly string[]; readonly verification: string; readonly effective?: boolean }

function requiredText(value: unknown, field: string): string { if (typeof value !== "string" || value.trim() === "") throw new TypeError(`${field} is required`); return value; }
function textArray(value: unknown, field: string): readonly string[] { if (!Array.isArray(value)) throw new TypeError(`${field} must be an array`); return value.map((item, index) => requiredText(item, `${field}[${index}]`)); }
function utc(value: unknown, field: string): string { const text = requiredText(value, field); if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(text) || !Number.isFinite(Date.parse(text))) throw new TypeError(`${field} must be UTC`); return text; }
function freeze<T>(value: T): T { if (value && typeof value === "object" && !Object.isFrozen(value)) { Object.freeze(value); for (const child of Object.values(value as Record<string, unknown>)) freeze(child); } return value; }

export function createCorrectiveAction(input: Partial<CorrectiveAction> & Pick<CorrectiveAction, "id" | "ownerId" | "dueAtUtc" | "evidence">): CorrectiveAction {
  const evidence = textArray(input.evidence, "evidence");
  return freeze({ id: requiredText(input.id, "id"), ownerId: requiredText(input.ownerId, "ownerId"), dueAtUtc: utc(input.dueAtUtc, "dueAtUtc"), evidence, ...(input.verification === undefined ? {} : { verification: requiredText(input.verification, "verification") }), ...(input.effectivenessReview === undefined ? {} : { effectivenessReview: requiredText(input.effectivenessReview, "effectivenessReview") }), ...(input.closureAuthorityId === undefined ? {} : { closureAuthorityId: requiredText(input.closureAuthorityId, "closureAuthorityId") }), status: input.status ?? "open" });
}

export function verifyCorrectiveAction(action: CorrectiveAction, input: VerificationInput): VerificationResult {
  if (action.evidence.length === 0) return freeze({ status: "blocked", evidenceRefs: [] });
  const reviewerId = requiredText(input.reviewerId, "reviewerId");
  const evidenceRefs = textArray(input.evidenceRefs, "evidenceRefs");
  requiredText(input.verification, "verification");
  return freeze({ status: input.effective === false ? "ineffective" : "verified", evidenceRefs, reviewerId });
}

export function closeCorrectiveAction(action: CorrectiveAction): CorrectiveAction {
  if (action.evidence.length === 0 || action.verification === undefined || action.effectivenessReview === undefined || action.closureAuthorityId === undefined) throw new Error("closure requires evidence, verification, effectiveness review, and closure authority");
  return freeze({ ...action, status: "closed" });
}
