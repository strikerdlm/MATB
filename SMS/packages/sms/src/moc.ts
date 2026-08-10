import type { MocCase } from "./types.js";

function requiredText(value: unknown, field: string): string { if (typeof value !== "string" || value.trim() === "") throw new TypeError(`${field} is required`); return value; }
function textArray(value: unknown, field: string): readonly string[] { if (!Array.isArray(value)) throw new TypeError(`${field} must be an array`); return value.map((item, index) => requiredText(item, `${field}[${index}]`)); }
function freeze<T>(value: T): T { if (value && typeof value === "object" && !Object.isFrozen(value)) { Object.freeze(value); for (const child of Object.values(value as Record<string, unknown>)) freeze(child); } return value; }

export function openManagementOfChange(input: MocCase): MocCase {
  return freeze({ id: requiredText(input.id, "id"), changeDescription: requiredText(input.changeDescription, "changeDescription"), ...(input.impactAnalysis === undefined ? {} : { impactAnalysis: requiredText(input.impactAnalysis, "impactAnalysis") }), affectedHazards: textArray(input.affectedHazards, "affectedHazards"), affectedRequirements: textArray(input.affectedRequirements, "affectedRequirements"), approvals: textArray(input.approvals, "approvals"), status: input.status ?? "open" });
}

export function completeMoc(input: MocCase, evidence: readonly string[]): MocCase {
  if (input.impactAnalysis === undefined || input.impactAnalysis.trim() === "") throw new Error("MOC completion requires impact analysis");
  const evidenceRefs = textArray(evidence, "verification evidence");
  if (input.approvals.length === 0) throw new Error("MOC completion requires approval");
  return freeze({ ...input, approvals: [...input.approvals, ...evidenceRefs], status: "verified" });
}
