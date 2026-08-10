import type { AuditFinding } from "./types.js";

function requiredText(value: unknown, field: string): string { if (typeof value !== "string" || value.trim() === "") throw new TypeError(`${field} is required`); return value; }
function textArray(value: unknown, field: string): readonly string[] { if (!Array.isArray(value) || value.length === 0) throw new TypeError(`${field} evidence is required`); return value.map((item, index) => requiredText(item, `${field}[${index}]`)); }
function utc(value: unknown, field: string): string { const text = requiredText(value, field); if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(text) || !Number.isFinite(Date.parse(text))) throw new TypeError(`${field} must be UTC`); return text; }
function freeze<T>(value: T): T { if (value && typeof value === "object" && !Object.isFrozen(value)) { Object.freeze(value); for (const child of Object.values(value as Record<string, unknown>)) freeze(child); } return value; }

export function createAuditFinding(input: AuditFinding): AuditFinding {
  const evidenceRefs = textArray(input.evidenceRefs, "evidenceRefs");
  return freeze({ id: requiredText(input.id, "id"), criterion: requiredText(input.criterion, "criterion"), scope: requiredText(input.scope, "scope"), evidenceRefs, ownerId: requiredText(input.ownerId, "ownerId"), dueAtUtc: utc(input.dueAtUtc, "dueAtUtc"), status: input.status === "closed" ? "closed" : "open" });
}
