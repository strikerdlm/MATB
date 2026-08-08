import { createInvalidationResult, type DependencyGraph, type GateName, type InvalidationResult, type MaterialChangeField, type MaterialChangeInput } from "./types.js";

const GATE_ORDER: readonly GateName[] = ["maintenance", "operator", "safety", "commander"];

/** The operational gates that must be re-approved for each material mission fact. */
const GATES_BY_FIELD: Readonly<Record<MaterialChangeField, readonly GateName[]>> = {
  aircraft: GATE_ORDER,
  gcs: GATE_ORDER,
  payload: GATE_ORDER,
  battery: GATE_ORDER,
  software: GATE_ORDER,
  crew: ["operator", "safety", "commander"],
  route: ["operator", "safety", "commander"],
  altitude: ["operator", "safety", "commander"],
  "visual-condition": ["operator", "safety", "commander"],
  schedule: ["operator", "safety", "commander"],
  weather: ["operator", "safety", "commander"],
  notam: ["operator", "safety", "commander"],
  aip: ["operator", "safety", "commander"],
  risk: ["safety", "commander"],
  mitigation: ["safety", "commander"],
  exception: ["safety", "commander"],
  policy: GATE_ORDER,
  evidence: GATE_ORDER,
  "display-note": [],
};

function compareStable(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && Object.getPrototypeOf(value) === Object.prototype;
}

/** Structural equality for JSON-like mission facts. Unsupported values fail closed. */
function sameFact(previous: unknown, next: unknown): boolean {
  if (Object.is(previous, next)) return true;
  if (typeof previous !== typeof next || previous === null || next === null) return false;
  if (Array.isArray(previous) || Array.isArray(next)) {
    if (!Array.isArray(previous) || !Array.isArray(next) || previous.length !== next.length) return false;
    return previous.every((value, index) => sameFact(value, next[index]));
  }
  if (isRecord(previous) && isRecord(next)) {
    const previousKeys = Object.keys(previous).sort(compareStable);
    const nextKeys = Object.keys(next).sort(compareStable);
    return previousKeys.length === nextKeys.length
      && previousKeys.every((key, index) => key === nextKeys[index] && sameFact(previous[key], next[key]));
  }
  return false;
}

function affectedRequirements(field: MaterialChangeField, graph: DependencyGraph): string[] {
  const ids = new Set<string>();
  for (const entry of graph.entries) {
    if (entry.field !== field) continue;
    for (const requirementId of entry.affectedRequirementIds) {
      if (requirementId.trim().length === 0) throw new RangeError("dependency requirement ID must not be empty");
      ids.add(requirementId);
    }
  }
  return [...ids].sort(compareStable);
}

/**
 * Returns the exact evaluation IDs supplied by the typed graph and the fixed
 * release gates that become unapproved. It never persists or carries approvals.
 */
export function invalidateForChange(input: MaterialChangeInput): InvalidationResult {
  if (sameFact(input.previous, input.next)) {
    return createInvalidationResult({ material: false, affectedRequirementIds: [], invalidatedGates: [], reason: "NO_EFFECTIVE_CHANGE" });
  }
  if (input.field === "display-note") {
    return createInvalidationResult({ material: false, affectedRequirementIds: [], invalidatedGates: [], reason: "NON_MATERIAL_DISPLAY_NOTE" });
  }
  return createInvalidationResult({
    material: true,
    affectedRequirementIds: affectedRequirements(input.field, input.dependencyGraph),
    invalidatedGates: GATES_BY_FIELD[input.field],
    reason: `MATERIAL_CHANGE_${input.field.toUpperCase().replaceAll("-", "_")}`,
  });
}
