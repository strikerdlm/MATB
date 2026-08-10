import { parseHazard, type Hazard } from "./types.js";

export interface MissionHazardInput {
  readonly id: string;
  readonly title: string;
  readonly description: string;
  readonly causes: readonly string[];
  readonly consequences: readonly string[];
  readonly residualRiskId: string;
}

export interface PromoteMissionHazardInput { readonly missionHazard: MissionHazardInput; readonly organizationalOwnerId: string; readonly promotedAtUtc?: string }
export interface PromotionResult { readonly hazard: Hazard; readonly sourceMissionId: string; readonly promotedAtUtc: string }

function requiredText(value: unknown, field: string): string { if (typeof value !== "string" || value.trim() === "") throw new TypeError(`${field} is required`); return value; }
function freeze<T>(value: T): T { if (value && typeof value === "object" && !Object.isFrozen(value)) { Object.freeze(value); for (const child of Object.values(value as Record<string, unknown>)) freeze(child); } return value; }

export function createHazard(input: unknown): Hazard { return parseHazard(input); }

export function promoteMissionHazard(input: PromoteMissionHazardInput): PromotionResult {
  const missionHazard = input?.missionHazard;
  if (missionHazard === undefined || missionHazard === null) throw new TypeError("missionHazard is required");
  const ownerId = requiredText(input.organizationalOwnerId, "organizationalOwnerId");
  const residualRiskId = requiredText(missionHazard.residualRiskId, "residualRiskId");
  const hazard = createHazard({ id: requiredText(missionHazard.id, "missionHazard.id"), title: requiredText(missionHazard.title, "missionHazard.title"), source: "mission", description: requiredText(missionHazard.description, "missionHazard.description"), causes: missionHazard.causes, consequences: missionHazard.consequences, ownerId, status: "open", riskAssessmentIds: [residualRiskId] });
  return freeze({ hazard, sourceMissionId: hazard.id, promotedAtUtc: input.promotedAtUtc ?? new Date().toISOString() });
}
