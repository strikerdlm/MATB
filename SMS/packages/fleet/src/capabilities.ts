import type { CapabilityBaseline, CapabilityClaim, CapabilityComparison, CapabilityRequirement, CapabilityResult } from "./types.js";
export function evaluateCapability(claim: CapabilityClaim, required: CapabilityRequirement | Record<string, unknown>, evidenceSnapshot: { current: boolean; acceptedEvidenceRefs: readonly string[]; approved?: boolean; asOfUtc: string; subjectId?: string }, legacyUseCase?: "operational" | "airworthiness" | "release" | "research"): CapabilityResult {
  const requirement = "conditions" in required ? required : { useCase: legacyUseCase ?? "operational", conditions: required };
  const useCase = requirement.useCase;
  const refs = claim.evidenceRefs;
  if (claim.confidence === "research-only") return { status: "unknown", reason: "RESEARCH_ONLY_EVIDENCE", evidenceRefs: refs };
  const asOf = Date.parse(evidenceSnapshot.asOfUtc);
  if (!Number.isFinite(asOf) || asOf < Date.parse(claim.validFromUtc) || (claim.validToUtc !== undefined && asOf >= Date.parse(claim.validToUtc))) return { status: "unknown", reason: "CAPABILITY_EVIDENCE_STALE", evidenceRefs: refs };
  if (evidenceSnapshot.subjectId !== undefined && evidenceSnapshot.subjectId !== claim.subjectId) return { status: "blocked", reason: "CAPABILITY_SUBJECT_MISMATCH", evidenceRefs: refs };
  if ((claim.confidence === "vendor-claimed" && useCase !== "research") || !evidenceSnapshot.current) return { status: "unknown", reason: claim.confidence === "vendor-claimed" ? "VENDOR_CLAIM_REQUIRES_REVIEW" : "EVIDENCE_NOT_CURRENT", evidenceRefs: refs };
  if (!evidenceSnapshot.approved && (useCase === "airworthiness" || useCase === "release" || requirement.hard === true)) return { status: "unknown", reason: "APPROVED_EVIDENCE_REQUIRED", evidenceRefs: refs };
  if (!refs.length || !refs.every((ref) => evidenceSnapshot.acceptedEvidenceRefs.includes(ref))) return { status: "unknown", reason: "ACCEPTED_EVIDENCE_REQUIRED", evidenceRefs: refs };
  for (const [key, expected] of Object.entries(requirement.conditions as Record<string, unknown>)) { const actual = key === "value" ? claim.value : claim.operatingConditions[key]; if (actual !== expected) return { status: "blocked", reason: "CAPABILITY_CONDITION_MISMATCH", evidenceRefs: refs }; }
  return { status: "pass", reason: "CAPABILITY_EVIDENCE_ACCEPTED", evidenceRefs: refs };
}
export function compareCapabilityBaselines(records: readonly CapabilityBaseline[]): CapabilityComparison { const all = new Set(records.flatMap((record) => record.capabilities)); const common = records.length ? [...all].filter((capability) => records.every((record) => record.capabilities.includes(capability))) : []; return { differences: [...all].filter((capability) => !common.includes(capability)).sort() }; }
