export type HazardSource = "mission" | "occurrence" | "audit" | "research-aggregate" | "management-of-change";
export type HazardStatus = "open" | "controlled" | "accepted" | "closed";

export interface Hazard {
  readonly id: string;
  readonly title: string;
  readonly source: HazardSource;
  readonly description: string;
  readonly causes: readonly string[];
  readonly consequences: readonly string[];
  readonly ownerId: string;
  readonly status: HazardStatus;
  readonly riskAssessmentIds: readonly string[];
}

export interface CorrectiveAction {
  readonly id: string;
  readonly ownerId: string;
  readonly dueAtUtc: string;
  readonly evidence: readonly string[];
  readonly verification?: string;
  readonly effectivenessReview?: string;
  readonly closureAuthorityId?: string;
  readonly status: "open" | "verified" | "closed";
}

export interface AuditFinding {
  readonly id: string;
  readonly criterion: string;
  readonly scope: string;
  readonly evidenceRefs: readonly string[];
  readonly ownerId: string;
  readonly dueAtUtc: string;
  readonly status: "open" | "closed";
}

export interface MocCase {
  readonly id: string;
  readonly changeDescription: string;
  readonly impactAnalysis?: string;
  readonly affectedHazards: readonly string[];
  readonly affectedRequirements: readonly string[];
  readonly approvals: readonly string[];
  readonly status: "open" | "approved" | "implemented" | "verified" | "closed";
}

export interface Occurrence {
  readonly id: string;
  readonly missionRevisionId: string;
  readonly reportedAtUtc: string;
  readonly classification: "incident" | "accident" | "hazard-report" | "equipment-damage" | "near-miss";
  readonly description: string;
  readonly reportingDeadlineUtc?: string;
  readonly status: "open" | "under-review" | "reported" | "closed";
  readonly evidenceRefs: readonly string[];
}

export interface ErpReadiness {
  readonly status: "ready" | "blocked" | "expired" | "unknown";
  readonly missing: readonly string[];
  readonly nextReviewAtUtc?: string;
}

export interface SpiStatus {
  readonly level: "normal" | "alert" | "action" | "unknown";
  readonly reason: string;
  readonly dataQuality: "complete" | "incomplete" | "stale";
}

export interface AlertLoadResult {
  readonly level: "low" | "moderate" | "high" | "unknown";
  readonly count: number;
  readonly unresolved: number;
  readonly escalationRequired: boolean;
  readonly evidenceRefs: readonly string[];
}

function isRecord(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === "object" && !Array.isArray(value); }
function requiredText(value: unknown, field: string): string { if (typeof value !== "string" || value.trim() === "") throw new TypeError(`${field} is required`); return value; }
function textArray(value: unknown, field: string): readonly string[] { if (!Array.isArray(value)) throw new TypeError(`${field} must be an array`); return value.map((item, index) => requiredText(item, `${field}[${index}]`)); }
function freeze<T>(value: T): T { if (value && typeof value === "object" && !Object.isFrozen(value)) { Object.freeze(value); for (const child of Object.values(value as Record<string, unknown>)) freeze(child); } return value; }
function strictKeys(value: Record<string, unknown>, allowed: readonly string[]): void { const unknown = Object.keys(value).find((key) => !allowed.includes(key)); if (unknown !== undefined) throw new TypeError(`unknown field: ${unknown}`); }

export function parseHazard(input: unknown): Hazard {
  if (!isRecord(input)) throw new TypeError("hazard must be an object");
  strictKeys(input, ["id", "title", "source", "description", "causes", "consequences", "ownerId", "status", "riskAssessmentIds"]);
  const source = requiredText(input.source, "source");
  const status = requiredText(input.status, "status");
  const sources: readonly HazardSource[] = ["mission", "occurrence", "audit", "research-aggregate", "management-of-change"];
  const statuses: readonly HazardStatus[] = ["open", "controlled", "accepted", "closed"];
  if (!sources.includes(source as HazardSource)) throw new TypeError("source is invalid");
  if (!statuses.includes(status as HazardStatus)) throw new TypeError("status is invalid");
  return freeze({ id: requiredText(input.id, "id"), title: requiredText(input.title, "title"), source: source as HazardSource, description: requiredText(input.description, "description"), causes: textArray(input.causes, "causes"), consequences: textArray(input.consequences, "consequences"), ownerId: requiredText(input.ownerId, "ownerId"), status: status as HazardStatus, riskAssessmentIds: textArray(input.riskAssessmentIds, "riskAssessmentIds") });
}
