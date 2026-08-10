export type OperationalQualificationStatus = "current" | "restricted" | "expired" | "unknown";
export type FatigueSelfDeclaration = "able" | "not-able" | "not-recorded";
export type WorkloadLevel = "low" | "moderate" | "high" | "unknown";

export interface OperationalHumanPerformanceStatus {
  readonly userId: string;
  readonly role: string;
  readonly dutyPeriodId: string;
  readonly qualificationStatus: OperationalQualificationStatus;
  readonly fatigueSelfDeclaration: FatigueSelfDeclaration;
  readonly screenExposureMinutes: number;
  readonly workloadLevel: WorkloadLevel;
  readonly alertLoad: number;
  readonly status: "available" | "restricted" | "unavailable" | "unknown";
  readonly evidenceRefs: readonly string[];
}

export interface WorkloadPulse {
  readonly userId: string;
  readonly missionRevisionId: string;
  readonly observedAtUtc: string;
  readonly level: WorkloadLevel;
  readonly source: "self-report" | "task-demand" | "alert-load";
  readonly evidenceRefs: readonly string[];
}

export interface CrmBrief {
  readonly missionRevisionId: string;
  readonly participants: readonly { readonly userId: string; readonly role: string }[];
  readonly communicationPlan: string;
  readonly transferOfControl: string;
  readonly incapacitationPlan: string;
  readonly acknowledgedBy: readonly string[];
}

export interface AlertLoadResult {
  readonly level: WorkloadLevel;
  readonly count: number;
  readonly unresolved: number;
  readonly escalationRequired: boolean;
  readonly evidenceRefs: readonly string[];
}

function isRecord(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === "object" && !Array.isArray(value); }
function requiredText(value: unknown, field: string): string { if (typeof value !== "string" || value.trim() === "") throw new TypeError(`${field} is required`); return value; }
function textArray(value: unknown, field: string): readonly string[] { if (!Array.isArray(value)) throw new TypeError(`${field} must be an array`); return value.map((item, index) => requiredText(item, `${field}[${index}]`)); }
function freeze<T>(value: T): T { if (value && typeof value === "object" && !Object.isFrozen(value)) { Object.freeze(value); for (const child of Object.values(value as Record<string, unknown>)) freeze(child); } return value; }
function enumValue<T extends string>(value: unknown, values: readonly T[], field: string): T { const candidate = requiredText(value, field) as T; if (!values.includes(candidate)) throw new TypeError(`${field} is invalid`); return candidate; }

export function parseOperationalHumanPerformanceStatus(input: unknown): OperationalHumanPerformanceStatus {
  if (!isRecord(input)) throw new TypeError("operational status must be an object");
  const allowed = ["userId", "role", "dutyPeriodId", "qualificationStatus", "fatigueSelfDeclaration", "screenExposureMinutes", "workloadLevel", "alertLoad", "status", "evidenceRefs"];
  const unknown = Object.keys(input).find((key) => !allowed.includes(key));
  if (unknown !== undefined) throw new TypeError(`unknown field: ${unknown}`);
  if (typeof input.screenExposureMinutes !== "number" || !Number.isFinite(input.screenExposureMinutes) || input.screenExposureMinutes < 0) throw new TypeError("screenExposureMinutes is invalid");
  if (typeof input.alertLoad !== "number" || !Number.isFinite(input.alertLoad) || input.alertLoad < 0) throw new TypeError("alertLoad is invalid");
  return freeze({ userId: requiredText(input.userId, "userId"), role: requiredText(input.role, "role"), dutyPeriodId: requiredText(input.dutyPeriodId, "dutyPeriodId"), qualificationStatus: enumValue(input.qualificationStatus, ["current", "restricted", "expired", "unknown"], "qualificationStatus"), fatigueSelfDeclaration: enumValue(input.fatigueSelfDeclaration, ["able", "not-able", "not-recorded"], "fatigueSelfDeclaration"), screenExposureMinutes: input.screenExposureMinutes, workloadLevel: enumValue(input.workloadLevel, ["low", "moderate", "high", "unknown"], "workloadLevel"), alertLoad: input.alertLoad, status: enumValue(input.status, ["available", "restricted", "unavailable", "unknown"], "status"), evidenceRefs: textArray(input.evidenceRefs, "evidenceRefs") });
}
