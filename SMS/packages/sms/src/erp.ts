import type { ErpReadiness } from "./types.js";

export interface ErpReadinessInput {
  readonly ownerId: string;
  readonly contactPlan: string;
  readonly aircraftContingencies: readonly string[];
  readonly crewContingencies: readonly string[];
  readonly routeContingencies: readonly string[];
  readonly exerciseDateUtc?: string;
  readonly nextReviewAtUtc?: string;
  readonly currentAtUtc: string;
}

function present(value: unknown): boolean { return typeof value === "string" ? value.trim() !== "" : Array.isArray(value) ? value.length > 0 : value !== undefined && value !== null; }
function validUtc(value: unknown): boolean { return typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(value) && Number.isFinite(Date.parse(value)); }
function freeze<T>(value: T): T { if (value && typeof value === "object" && !Object.isFrozen(value)) { Object.freeze(value); for (const child of Object.values(value as Record<string, unknown>)) freeze(child); } return value; }

export function evaluateErpReadiness(input: ErpReadinessInput): ErpReadiness {
  if (!validUtc(input.currentAtUtc)) return freeze({ status: "unknown", missing: ["currentAtUtc"] });
  const missing = [
    ...(!present(input.ownerId) ? ["ownerId"] : []),
    ...(!present(input.contactPlan) ? ["contactPlan"] : []),
    ...(!present(input.aircraftContingencies) ? ["aircraftContingencies"] : []),
    ...(!present(input.crewContingencies) ? ["crewContingencies"] : []),
    ...(!present(input.routeContingencies) ? ["routeContingencies"] : []),
    ...(!validUtc(input.exerciseDateUtc) ? ["exerciseDateUtc"] : []),
    ...(!validUtc(input.nextReviewAtUtc) ? ["nextReviewAtUtc"] : []),
  ];
  if (missing.length > 0) return freeze({ status: "blocked", missing });
  if (Date.parse(input.nextReviewAtUtc!) <= Date.parse(input.currentAtUtc)) return freeze({ status: "expired", missing: [], nextReviewAtUtc: input.nextReviewAtUtc });
  return freeze({ status: "ready", missing: [], nextReviewAtUtc: input.nextReviewAtUtc });
}
