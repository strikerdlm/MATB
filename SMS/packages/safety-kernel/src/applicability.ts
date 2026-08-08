import type { NormalizedRequirement } from "@fac-isr/evidence";
import type { AircraftClass, ApplicabilityResult, MissionRevision, PolicyPackage, RuleEvaluation, SafetyBlocker } from "./types.js";
import { CONCEPT_IDS } from "./terminology.js";

export interface ApplicabilityPolicy extends Partial<PolicyPackage> {
  policy?: ApplicabilityPolicy;
  status?: PolicyPackage["status"];
  autonomousFlightProhibited?: boolean;
  supervisedAutomationApproved?: boolean;
  humanInterventionRequired?: boolean;
  ifrApproved?: boolean;
  flightRuleApproved?: boolean;
  approvedCapabilityEvidence?: boolean;
  automationMode?: ApplicabilityFacts["automationMode"];
  humanInterventionCapable?: boolean;
  aircraftEquipmentCapable?: boolean;
  segregatedAirspace?: boolean;
  authorizationEvidence?: boolean;
}

export interface ApplicabilityFacts {
  readonly mtowKg?: number;
  readonly automationMode?: "manual" | "supervised" | "autonomous";
  readonly humanInterventionCapable?: boolean;
  readonly approvedCapabilityEvidence?: boolean;
  readonly aircraftEquipmentCapable?: boolean;
  readonly segregatedAirspace?: boolean;
  readonly authorizationEvidence?: boolean;
  readonly flightRuleApproved?: boolean;
  readonly operational?: boolean;
  readonly researchOnly?: boolean;
  readonly swarm?: boolean;
  readonly assignedOperatorIds?: Readonly<Record<string, string>>;
  readonly crew?: MissionRevision["crew"];
  readonly policy?: ApplicabilityPolicy;
  readonly [key: string]: unknown;
}

type RequirementLike = Pick<NormalizedRequirement, "requirementId" | "applicabilityExpression" | "severity"> & Partial<NormalizedRequirement>;

const HARD_GATES: RuleEvaluation["affectedGates"] = ["operator", "safety", "commander"];

export function getClassBand(mtowKg: number): AircraftClass {
  if (!Number.isFinite(mtowKg) || mtowKg < 0.015) throw new RangeError("MTOW must be finite and at least 0.015 kg");
  if (mtowKg < 7) return "IA";
  if (mtowKg < 15) return "IB";
  if (mtowKg < 150) return "IC";
  if (mtowKg === 150) throw new RangeError("MTOW 150 kg is unclassified");
  if (mtowKg <= 600) return "II";
  return "III";
}

function blocker(code: string, conceptId: string, explanationKey: string, severity: SafetyBlocker["severity"] = "hard", evidenceRefs: readonly string[] = []): SafetyBlocker {
  return { code, conceptId, explanationKey, severity, evidenceRefs };
}

function assignedQualifiedOperator(mission: MissionRevision, aircraftId: string, facts: ApplicabilityFacts): boolean {
  const aircraft = mission.aircraft.find((item) => item.aircraftId === aircraftId);
  const operatorId = aircraft?.operatorUserId ?? facts.assignedOperatorIds?.[aircraftId];
  if (!operatorId) return false;
  return mission.crew.some((crew) => crew.userId === operatorId && crew.role === "operator" && (crew.aircraftId === aircraftId || (crew.aircraftId === undefined && mission.aircraft.length === 1)) && crew.qualified && crew.recencyCurrent && crew.dutyStatus === "available");
}

export function buildHardBlockers(mission: MissionRevision, facts: ApplicabilityFacts = {}): SafetyBlocker[] {
  const blockers: SafetyBlocker[] = [];
  const configuration = mission.configuration;
  const operational = facts.operational ?? mission.profileId === "fac-state-aviation";
  const facProfile = mission.profileId === "fac-state-aviation";
  if ((facProfile || operational) && (configuration === "armed" || configuration === "strike" || mission.aircraft.some((aircraft) => aircraft.configuration === "armed" || aircraft.configuration === "strike"))) {
    blockers.push(blocker("CONFIGURATION_OUT_OF_SCOPE", CONCEPT_IDS.configurationOutOfScope, "configurationOutOfScope"));
  }
  const crewMission = facts.crew ? { ...mission, crew: facts.crew } : mission;
  const operatorRequired = mission.state === "Active" || operational;
  if (operatorRequired && mission.aircraft.some((aircraft) => !assignedQualifiedOperator(crewMission, aircraft.aircraftId, facts))) {
    blockers.push(blocker("MISSING_OPERATOR_PER_AIRCRAFT", CONCEPT_IDS.missingOperatorPerAircraft, "missingOperatorPerAircraft"));
  }
  const assignments = mission.aircraft.map((aircraft) => aircraft.operatorUserId ?? facts.assignedOperatorIds?.[aircraft.aircraftId]).filter((id): id is string => Boolean(id));
  const oneToMany = new Set(assignments).size < assignments.length;
  if (mission.aircraft.length > 1 && (facts.swarm === true || facts.researchOnly === true || oneToMany)) {
    blockers.push(blocker("SWARM_RESEARCH_NON_DISPATCHABLE", CONCEPT_IDS.swarmResearchNonDispatchable, "swarmResearchNonDispatchable", "policy"));
  }
  if (facts.automationMode === "autonomous") {
    blockers.push(blocker("AUTONOMOUS_FLIGHT_PROHIBITED", CONCEPT_IDS.autonomousFlightProhibited, "autonomousFlightProhibited"));
  }
  return blockers;
}

function evidenceResult(complete: boolean, applicable: boolean, reason: string, affectedGates: RuleEvaluation["affectedGates"] = HARD_GATES): ApplicabilityResult {
  return { applicable, result: complete ? "pass" : "unknown", reason, affectedGates };
}

export function evaluateApplicability(mission: MissionRevision, requirement: RequirementLike, policy?: PolicyPackage | ApplicabilityPolicy, facts: ApplicabilityFacts = {}): ApplicabilityResult {
  // Accept the public three-argument form while allowing facts to be supplied as policy metadata.
  const supplied = (policy ?? {}) as ApplicabilityPolicy;
  const merged: ApplicabilityFacts = { ...facts, ...(supplied.policy ?? {}), ...supplied };
  const expression = requirement.applicabilityExpression.toLowerCase();
  const applicable = expression.includes("ifr") ? mission.flightRule === "IFR" : expression.includes("autonomous") || expression.includes("supervised") || expression.includes("state_aviation") ? mission.profileId === "fac-state-aviation" : true;
  if (!applicable) return { applicable: false, result: "not-reviewed", reason: "REQUIREMENT_NOT_APPLICABLE", affectedGates: [] };
  const autonomousRequirement = expression.includes("autonomous");
  if (autonomousRequirement) {
    if (merged.automationMode === "autonomous") return { applicable: true, result: "fail", reason: "AUTONOMOUS_FLIGHT_PROHIBITED", affectedGates: HARD_GATES };
    if (merged.automationMode === undefined) return evidenceResult(false, true, "AUTOMATION_MODE_REQUIRED");
    return { applicable: false, result: "not-reviewed", reason: "AUTONOMOUS_MODE_NOT_SELECTED", affectedGates: [] };
  }
  if (requirement.interpretationStatus === "draft" || requirement.interpretationStatus === "superseded") return { applicable: true, result: "not-reviewed", reason: "REQUIREMENT_NOT_REVIEWED", affectedGates: HARD_GATES };
  if (requirement.interpretationStatus === "qualified-review") return evidenceResult(false, true, "REQUIREMENT_SOURCE_REVIEW_PENDING");
  if ((requirement.sourceRefs ?? []).some((sourceRef) => sourceRef.reviewState !== "accepted")) return evidenceResult(false, true, "REQUIREMENT_EVIDENCE_NOT_ACCEPTED");
  const acceptedEvidence = (requirement.sourceRefs ?? []).some((sourceRef) => sourceRef.reviewState === "accepted");
  const evidenceRequired = requirement.evidenceRequired === true || requirement.severity === "hard";
  if (evidenceRequired && !acceptedEvidence) return evidenceResult(false, true, "ACCEPTED_EVIDENCE_REQUIRED");
  const policyDependent = evidenceRequired || expression.includes("ifr") || expression.includes("supervised") || expression.includes("state_aviation");
  if (merged.status !== "approved" && policyDependent) return evidenceResult(false, true, "APPROVED_POLICY_REQUIRED");
  if (merged.automationMode === "supervised" || expression.includes("supervised_automation")) {
    const complete = merged.supervisedAutomationApproved === true && (merged.humanInterventionCapable ?? false) && (merged.approvedCapabilityEvidence ?? merged.approvedCapabilityEvidence === true);
    return evidenceResult(complete, true, complete ? "SUPERVISED_AUTOMATION_EVIDENCE_ACCEPTED" : "SUPERVISED_AUTOMATION_EVIDENCE_INCOMPLETE");
  }
  if (mission.flightRule === "IFR" || expression.includes("ifr")) {
    const complete = (merged.ifrApproved ?? merged.flightRuleApproved) === true && merged.aircraftEquipmentCapable === true && merged.segregatedAirspace === true && merged.authorizationEvidence === true;
    return evidenceResult(complete, true, complete ? "IFR_EVIDENCE_ACCEPTED" : "IFR_EVIDENCE_INCOMPLETE");
  }
  return { applicable: true, result: "pass", reason: "REQUIREMENT_APPLICABLE", affectedGates: HARD_GATES };
}
