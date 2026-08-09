import type { Discrepancy, MaintenanceEvaluation, MaintenanceRelease } from "./types.js";
export interface ApprovedDeferral { id: string; authorizedBy: string; evidenceRefs: readonly string[]; validUntilUtc: string }
export interface MaintenanceReleaseInput { release: MaintenanceRelease; aircraftId: string; configurationHash: string; softwareBaseline: string; asOfUtc: string; evidenceRefs: readonly string[]; acceptedEvidenceRefs: readonly string[]; approvedDeferrals?: readonly ApprovedDeferral[] }
function parseUtc(value: string): number | undefined { const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/.exec(value); if (!m) return undefined; const date = new Date(value); if (!Number.isFinite(date.getTime()) || date.getUTCFullYear() !== +m[1] || date.getUTCMonth() + 1 !== +m[2] || date.getUTCDate() !== +m[3] || date.getUTCHours() !== +m[4] || date.getUTCMinutes() !== +m[5] || date.getUTCSeconds() !== +m[6]) return undefined; return date.getTime(); }
export function isMinimumEquipmentSatisfied(input: MaintenanceRelease): boolean { return input.minimumEquipmentSatisfied; }
export function classifyDiscrepancy(discrepancy: Discrepancy, approvedDeferrals: readonly ApprovedDeferral[], asOfUtc?: string, acceptedEvidenceRefs: readonly string[] = []): "open" | "deferred" | "blocking" { if (discrepancy.disposition === "resolved") return "open"; const deferral = approvedDeferrals.find((item) => item.id === discrepancy.id); if (deferral && asOfUtc !== undefined && parseUtc(deferral.validUntilUtc)! > parseUtc(asOfUtc)! && deferral.authorizedBy.trim() !== "" && deferral.evidenceRefs.length > 0 && deferral.evidenceRefs.every((ref) => acceptedEvidenceRefs.includes(ref))) return "deferred"; return "blocking"; }
export function evaluateMaintenanceRelease(input: MaintenanceReleaseInput): MaintenanceEvaluation {
  const blockers: string[] = [];
  const asOf = parseUtc(input.asOfUtc); const due = parseUtc(input.release.inspectionDueAtUtc); const signed = parseUtc(input.release.signedAtUtc);
  if (asOf === undefined || due === undefined || signed === undefined) return { status: "unknown", blockers: ["UTC_TIMESTAMP_INVALID"], evidenceRefs: input.evidenceRefs };
  if (input.release.aircraftId !== input.aircraftId) blockers.push("AIRCRAFT_ID_MISMATCH");
  if (input.release.configurationHash !== input.configurationHash) blockers.push("CONFIGURATION_HASH_MISMATCH");
  if (asOf >= due) blockers.push("INSPECTION_OVERDUE");
  if (!isMinimumEquipmentSatisfied(input.release)) blockers.push("MINIMUM_EQUIPMENT_UNSATISFIED");
  if (input.release.batteryRelease !== "released") blockers.push("BATTERY_NOT_RELEASED");
  if (input.release.payloadRelease !== "released") blockers.push("PAYLOAD_NOT_RELEASED");
  if (input.release.softwareBaseline !== input.softwareBaseline) blockers.push("SOFTWARE_BASELINE_MISMATCH");
  if (input.release.decision !== "released" || !input.release.authorizedBy || input.release.authorizedBy.trim() === "" || signed > asOf) blockers.push("RETURN_TO_SERVICE_NOT_AUTHORIZED");
  for (const discrepancy of input.release.openDiscrepancies) if (classifyDiscrepancy(discrepancy, input.approvedDeferrals ?? [], input.asOfUtc, input.acceptedEvidenceRefs) === "blocking") blockers.push(`DISCREPANCY_BLOCKING:${discrepancy.id}`);
  const missingEvidence = input.evidenceRefs.length === 0 || input.evidenceRefs.some((ref) => ref.trim() === "") || !input.evidenceRefs.every((ref) => input.acceptedEvidenceRefs.includes(ref));
  if (missingEvidence) blockers.push("ACCEPTED_MAINTENANCE_EVIDENCE_REQUIRED");
  if (blockers.length) return { status: missingEvidence && blockers.length === 1 ? "unknown" : "blocked", blockers, evidenceRefs: input.evidenceRefs };
  return { status: blockers.length ? "blocked" : "pass", blockers, evidenceRefs: input.evidenceRefs };
}
