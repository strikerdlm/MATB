import { parseOperationalHumanPerformanceStatus, type AlertLoadResult, type CrmBrief, type OperationalHumanPerformanceStatus, type WorkloadPulse } from "./types.js";

export interface HumanPerformancePolicy { readonly maxScreenExposureMinutes: number; readonly maxAlertLoad: number; readonly policyVersion: string }
export interface AlertEvent { readonly severity: "info" | "warning" | "blocker"; readonly acknowledged: boolean; readonly duplicate?: boolean }
export interface AlertLoadPolicy { readonly escalateAtUnresolved: number; readonly policyVersion: string }

function requiredText(value: unknown, field: string): string { if (typeof value !== "string" || value.trim() === "") throw new TypeError(`${field} is required`); return value; }
function textArray(value: unknown, field: string): readonly string[] { if (!Array.isArray(value)) throw new TypeError(`${field} must be an array`); return value.map((item, index) => requiredText(item, `${field}[${index}]`)); }
function utc(value: unknown, field: string): string { const text = requiredText(value, field); if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(text) || !Number.isFinite(Date.parse(text))) throw new TypeError(`${field} must be UTC`); return text; }
function freeze<T>(value: T): T { if (value && typeof value === "object" && !Object.isFrozen(value)) { Object.freeze(value); for (const child of Object.values(value as Record<string, unknown>)) freeze(child); } return value; }

export function evaluateOperationalStatus(input: unknown, policy: HumanPerformancePolicy): OperationalHumanPerformanceStatus {
  if (!Number.isFinite(policy.maxScreenExposureMinutes) || policy.maxScreenExposureMinutes < 0 || !Number.isFinite(policy.maxAlertLoad) || policy.maxAlertLoad < 0) throw new TypeError("human-performance policy limits are invalid");
  const parsed = parseOperationalHumanPerformanceStatus(input);
  const restricted = parsed.screenExposureMinutes > policy.maxScreenExposureMinutes || parsed.alertLoad > policy.maxAlertLoad || parsed.fatigueSelfDeclaration === "not-able" || parsed.qualificationStatus === "expired" || parsed.qualificationStatus === "restricted";
  const status = parsed.status === "unavailable" ? "unavailable" : restricted ? "restricted" : parsed.status;
  return freeze({ ...parsed, status, evidenceRefs: [...parsed.evidenceRefs, `policy:${requiredText(policy.policyVersion, "policyVersion")}`] });
}

export function recordWorkloadPulse(input: WorkloadPulse): WorkloadPulse {
  const level = input.level;
  const levels: readonly WorkloadPulse["level"][] = ["low", "moderate", "high", "unknown"];
  if (!levels.includes(level)) throw new TypeError("workload level is invalid");
  return freeze({ userId: requiredText(input.userId, "userId"), missionRevisionId: requiredText(input.missionRevisionId, "missionRevisionId"), observedAtUtc: utc(input.observedAtUtc, "observedAtUtc"), level, source: input.source, evidenceRefs: textArray(input.evidenceRefs, "evidenceRefs") });
}

export function evaluateAlertLoad(events: readonly AlertEvent[], policy: AlertLoadPolicy): AlertLoadResult {
  if (!Number.isInteger(policy.escalateAtUnresolved) || policy.escalateAtUnresolved < 1) throw new TypeError("escalateAtUnresolved is invalid");
  const unresolved = events.filter((event) => !event.acknowledged).length;
  const level = unresolved >= policy.escalateAtUnresolved ? "high" : unresolved > 0 ? "moderate" : "low";
  return freeze({ level, count: events.length, unresolved, escalationRequired: unresolved >= policy.escalateAtUnresolved, evidenceRefs: [`policy:${requiredText(policy.policyVersion, "policyVersion")}`] });
}

export function createCrmBrief(input: CrmBrief): CrmBrief {
  if (!Array.isArray(input.participants) || input.participants.length === 0) throw new TypeError("participants are required");
  if (input.participants.some((participant) => requiredText(participant.userId, "participant.userId") === "" || requiredText(participant.role, "participant.role") === "")) throw new TypeError("participant is invalid");
  const communicationPlan = requiredText(input.communicationPlan, "communicationPlan");
  const transferOfControl = requiredText(input.transferOfControl, "transferOfControl");
  const incapacitationPlan = requiredText(input.incapacitationPlan, "incapacitationPlan");
  return freeze({ missionRevisionId: requiredText(input.missionRevisionId, "missionRevisionId"), participants: input.participants.map((participant) => ({ userId: requiredText(participant.userId, "participant.userId"), role: requiredText(participant.role, "participant.role") })), communicationPlan, transferOfControl, incapacitationPlan, acknowledgedBy: textArray(input.acknowledgedBy, "acknowledgedBy") });
}
