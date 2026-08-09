import type {
  AircraftClass,
  CrewAssignment,
  FleetSafetyFacts,
  GateName,
  MissionRevision,
  RuleEvaluation,
  SafetyBlocker,
} from "./types.js";
import { CONCEPT_IDS } from "./terminology.js";

type FleetStatus = "pass" | "blocked" | "unknown";

export interface FleetAircraftInput {
  aircraftId?: string;
  id?: string;
  aircraftClass?: AircraftClass;
}

export interface FleetMaintenanceInput {
  aircraftId: string;
  status: FleetStatus;
  evidenceRefs?: readonly string[];
}

export interface FleetEnergyInput {
  aircraftId: string;
  status: FleetStatus;
  evidenceRefs?: readonly string[];
  evidenceRef?: string;
}

function nonempty(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function unique(values: readonly string[]): string[] {
  return [...new Set(values.filter(nonempty))];
}

function assertKnownAircraft(aircraftIds: ReadonlySet<string>, aircraftId: string): void {
  if (!nonempty(aircraftId) || !aircraftIds.has(aircraftId)) throw new RangeError("fleet fact references an unknown aircraft");
}

function aircraftIdOf(input: FleetAircraftInput): string {
  return input.aircraftId ?? input.id ?? "";
}

/** Maps fleet/maintenance/energy package results into the kernel's stable fact shape. */
export function buildFleetSafetyFacts(
  fleet: readonly FleetAircraftInput[],
  maintenance: readonly FleetMaintenanceInput[],
  crew: readonly CrewAssignment[],
  energy: readonly FleetEnergyInput[],
): FleetSafetyFacts {
  const aircraftIds = fleet.map(aircraftIdOf);
  if (aircraftIds.length === 0 || aircraftIds.some((aircraftId) => !nonempty(aircraftId)) || new Set(aircraftIds).size !== aircraftIds.length) {
    throw new RangeError("fleet must contain unique aircraft IDs");
  }
  const knownAircraft = new Set(aircraftIds);
  for (const record of [...maintenance, ...energy]) assertKnownAircraft(knownAircraft, record.aircraftId);

  const maintenanceFacts = aircraftIds.map((aircraftId) => {
    const record = maintenance.find((candidate) => candidate.aircraftId === aircraftId);
    return { aircraftId, status: record?.status ?? "unknown" as const, evidenceRefs: unique(record?.evidenceRefs ?? []) };
  });
  const energyFacts = aircraftIds.map((aircraftId) => {
    const record = energy.find((candidate) => candidate.aircraftId === aircraftId);
    const evidenceRef = record?.evidenceRef ?? record?.evidenceRefs?.find(nonempty) ?? "";
    return { aircraftId, status: record?.status ?? "unknown" as const, evidenceRef };
  });
  return {
    maintenance: maintenanceFacts,
    crew: crew.map((member) => ({ ...member })),
    energy: energyFacts,
  };
}

export interface FleetEvaluation {
  evaluations: RuleEvaluation[];
  blockers: SafetyBlocker[];
}

function fleetEvaluation(
  requirementId: string,
  result: RuleEvaluation["result"],
  reason: string,
  evidenceRefs: readonly string[],
  affectedGates: readonly GateName[],
): RuleEvaluation {
  return {
    requirementId,
    result,
    severity: "hard",
    reason,
    evidenceRefs: unique(evidenceRefs),
    affectedGates,
  };
}

function fleetBlocker(
  code: string,
  reason: string,
  severity: SafetyBlocker["severity"],
  evidenceRefs: readonly string[],
): SafetyBlocker {
  return {
    code,
    conceptId: CONCEPT_IDS.requirementFailed,
    severity,
    explanationKey: reason,
    evidenceRefs: unique(evidenceRefs),
  };
}

export function evaluateFleetFacts(mission: MissionRevision, facts: FleetSafetyFacts): FleetEvaluation {
  const evaluations: RuleEvaluation[] = [];
  const blockers: SafetyBlocker[] = [];
  for (const aircraft of mission.aircraft) {
    const maintenance = facts.maintenance.find((record) => record.aircraftId === aircraft.aircraftId);
    const maintenanceEvidence = maintenance?.evidenceRefs ?? [];
    if (maintenance?.status === "pass") {
      evaluations.push(fleetEvaluation("maintenance.release", "pass", "MAINTENANCE_RELEASE_ACCEPTED", maintenanceEvidence, ["maintenance"]));
    } else if (maintenance?.status === "blocked") {
      evaluations.push(fleetEvaluation("maintenance.release", "fail", "INVALID_MAINTENANCE_RELEASE", maintenanceEvidence, ["maintenance"]));
      blockers.push(fleetBlocker("INVALID_MAINTENANCE_RELEASE", "INVALID_MAINTENANCE_RELEASE", "hard", maintenanceEvidence));
    } else {
      evaluations.push(fleetEvaluation("maintenance.release", "unknown", "MAINTENANCE_EVIDENCE_UNKNOWN", maintenanceEvidence, ["maintenance"]));
      blockers.push(fleetBlocker("MAINTENANCE_EVIDENCE_UNKNOWN", "MAINTENANCE_EVIDENCE_UNKNOWN", "data", maintenanceEvidence));
    }

    const energy = facts.energy.find((record) => record.aircraftId === aircraft.aircraftId);
    const energyEvidence = energy?.evidenceRef === undefined || !nonempty(energy.evidenceRef) ? [] : [energy.evidenceRef];
    if (energy?.status === "pass") {
      evaluations.push(fleetEvaluation("energy.reserve", "pass", "ENERGY_RESERVE_ACCEPTED", energyEvidence, ["safety", "commander"]));
    } else if (energy?.status === "blocked") {
      evaluations.push(fleetEvaluation("energy.reserve", "fail", "INSUFFICIENT_RESERVE", energyEvidence, ["safety", "commander"]));
      blockers.push(fleetBlocker("INSUFFICIENT_RESERVE", "INSUFFICIENT_RESERVE", "hard", energyEvidence));
    } else {
      evaluations.push(fleetEvaluation("energy.reserve", "unknown", "ENERGY_EVIDENCE_UNKNOWN", energyEvidence, ["safety", "commander"]));
      blockers.push(fleetBlocker("ENERGY_EVIDENCE_UNKNOWN", "ENERGY_EVIDENCE_UNKNOWN", "data", energyEvidence));
    }
  }
  return { evaluations, blockers };
}
