import type {
  CrewAssignment,
  FleetCrewFact,
  FleetEnergyFact,
  FleetFactStatus,
  FleetSafetyFact,
  FleetSafetyFacts,
} from "./types.js";

export interface FleetFactInput {
  aircraftId: string;
  status: FleetFactStatus;
  blockers?: readonly string[];
  evidenceRefs?: readonly string[];
}

export interface FleetSourceInput {
  aircraft: readonly FleetFactInput[];
  capability?: readonly FleetFactInput[];
  battery?: readonly FleetFactInput[];
}

export type CrewEvaluationStatus = FleetFactStatus | "available" | "restricted" | "unavailable";

export interface CrewEvaluationInput {
  aircraftId?: string;
  status: CrewEvaluationStatus;
  blockers?: readonly string[];
  evidenceRefs?: readonly string[];
}

export interface CrewSourceInput {
  assignments: readonly CrewAssignment[];
  evaluations: readonly CrewEvaluationInput[];
}

export interface EnergySafetyInput extends FleetFactInput {
  recoveryPercent?: number;
  diversionPercent?: number;
  contingencyPercent?: number;
  predictedAtRecoveryPercent?: number;
  diversionReservePercent?: number;
  contingencyReservePercent?: number;
  uncertaintyPercent?: number;
  limitingAssumption?: string;
}

function collect(values: readonly string[] | undefined): string[] {
  const result: string[] = [];
  const seen = new Set<string>();
  for (const value of values ?? []) {
    if (typeof value !== "string") continue;
    const normalized = value.trim();
    if (normalized === "" || seen.has(normalized)) continue;
    seen.add(normalized);
    result.push(normalized);
  }
  return result;
}

function aircraftId(value: unknown): string {
  return typeof value === "string" && value.length > 0 && value === value.trim() ? value : "";
}

function normalizeFact(input: FleetFactInput | undefined): FleetSafetyFact {
  const id = aircraftId(input?.aircraftId);
  const blockers = collect(input?.blockers);
  const evidenceRefs = collect(input?.evidenceRefs);
  const status = input?.status === "pass" || input?.status === "blocked" || input?.status === "unknown"
    ? input.status
    : "unknown";
  if (id === "") blockers.push("FACT_AIRCRAFT_ID_UNKNOWN");
  if (input?.status !== "pass" && input?.status !== "blocked" && input?.status !== "unknown") blockers.push("FACT_STATUS_UNKNOWN");
  return { aircraftId: id, status, blockers: [...new Set(blockers)], evidenceRefs };
}

function normalizeCrewStatus(status: CrewEvaluationStatus | undefined): { status: FleetFactStatus; invalid: boolean } {
  if (status === "pass" || status === "available") return { status: "pass", invalid: false };
  if (status === "blocked" || status === "restricted" || status === "unavailable") return { status: "blocked", invalid: false };
  if (status === "unknown") return { status: "unknown", invalid: false };
  return { status: "unknown", invalid: true };
}

function normalizeCrew(input: CrewEvaluationInput): FleetCrewFact {
  const normalizedStatus = normalizeCrewStatus(input.status);
  const blockers = collect(input.blockers);
  if (normalizedStatus.invalid) blockers.push("CREW_STATUS_UNKNOWN");
  const id = input.aircraftId === undefined ? undefined : aircraftId(input.aircraftId);
  if (input.aircraftId !== undefined && id === "") blockers.push("FACT_AIRCRAFT_ID_UNKNOWN");
  return {
    ...(id === undefined ? {} : { aircraftId: id }),
    status: normalizedStatus.status,
    blockers: [...new Set(blockers)],
    evidenceRefs: collect(input.evidenceRefs),
  };
}

function normalizeEnergy(input: EnergySafetyInput): FleetEnergyFact {
  const fact = normalizeFact(input);
  const evidenceRefs = fact.evidenceRefs ?? [];
  const recoveryPercent = input.predictedAtRecoveryPercent ?? input.recoveryPercent;
  const diversionPercent = input.diversionReservePercent ?? input.diversionPercent;
  const contingencyPercent = input.contingencyReservePercent ?? input.contingencyPercent;
  return {
    ...fact,
    ...(evidenceRefs[0] === undefined ? {} : { evidenceRef: evidenceRefs[0] }),
    ...(Number.isFinite(recoveryPercent) ? { recoveryPercent } : {}),
    ...(Number.isFinite(diversionPercent) ? { diversionPercent } : {}),
    ...(Number.isFinite(contingencyPercent) ? { contingencyPercent } : {}),
    ...(Number.isFinite(input.uncertaintyPercent) ? { uncertaintyPercent: input.uncertaintyPercent } : {}),
    limitingAssumption: typeof input.limitingAssumption === "string" && input.limitingAssumption.trim() !== ""
      ? input.limitingAssumption
      : "ENERGY_LIMITING_ASSUMPTION_UNKNOWN",
  };
}

function freezeArray<T>(values: readonly T[]): readonly T[] {
  return Object.freeze([...values]);
}

/** Converts fleet-package evaluations into the normalized facts consumed by the safety kernel. */
export function buildFleetSafetyFacts(
  fleet: FleetSourceInput,
  maintenance: readonly FleetFactInput[],
  crew: CrewSourceInput,
  energy: readonly EnergySafetyInput[],
): FleetSafetyFacts {
  return Object.freeze({
    fleet: freezeArray((fleet?.aircraft ?? []).map(normalizeFact)),
    capability: freezeArray((fleet?.capability ?? []).map(normalizeFact)),
    battery: freezeArray((fleet?.battery ?? []).map(normalizeFact)),
    maintenance: freezeArray((maintenance ?? []).map(normalizeFact)),
    crew: freezeArray(crew?.assignments ?? []),
    crewEvaluations: freezeArray((crew?.evaluations ?? []).map(normalizeCrew)),
    energy: freezeArray((energy ?? []).map(normalizeEnergy)),
  });
}
