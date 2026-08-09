import type { NormalizedRequirement } from "@fac-isr/evidence";
import { buildHardBlockers, evaluateApplicability } from "./applicability.js";
import { CONCEPT_IDS, CONCEPT_LABELS, type ConceptId } from "./terminology.js";
import { createSafetyEvaluationResult, type FleetCrewFact, type FleetEnergyFact, type FleetSafetyFact, type FleetSafetyFacts, type GateName, type LocalizedExplanation, type RuleEvaluation, type SafetyBlocker, type SafetyEvaluationInput, type SafetyEvaluationResult } from "./types.js";

const KERNEL_VERSION = "0.1.0";
const GATE_ORDER: readonly GateName[] = ["maintenance", "operator", "safety", "commander"];
const HARD_BLOCKER_GATES: readonly GateName[] = ["operator", "safety", "commander"];
const UTC_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/;

type FreshnessResult = Pick<RuleEvaluation, "result" | "reason" | "evidenceRefs"> | undefined;

function evidenceIds(requirement: NormalizedRequirement): string[] {
  return requirement.sourceRefs.map((sourceRef) => sourceRef.evidenceId);
}

function parseUtc(value: string): number {
  const match = UTC_PATTERN.exec(value);
  if (!match) throw new RangeError("timestamp must be a valid UTC ISO-8601 instant");
  const [, year, month, day, hour, minute, second, fraction = ""] = match;
  const timestamp = Date.parse(value);
  const date = new Date(timestamp);
  if (!Number.isFinite(timestamp)
    || date.getUTCFullYear() !== Number(year)
    || date.getUTCMonth() + 1 !== Number(month)
    || date.getUTCDate() !== Number(day)
    || date.getUTCHours() !== Number(hour)
    || date.getUTCMinutes() !== Number(minute)
    || date.getUTCSeconds() !== Number(second)
    || date.getUTCMilliseconds() !== Number(fraction.padEnd(3, "0") || 0)) {
    throw new RangeError("timestamp must be a valid UTC ISO-8601 instant");
  }
  return timestamp;
}

function compareStable(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function policyFreshness(input: SafetyEvaluationInput, sourceEvidenceIds: readonly string[]): FreshnessResult {
  const { policy } = input;
  if (policy?.status === "expired") return { result: "expired", reason: "POLICY_EXPIRED", evidenceRefs: [...sourceEvidenceIds, policy.packageId] };
  const expiresAtUtc = policy?.manifest?.expiresAtUtc;
  if (expiresAtUtc && parseUtc(expiresAtUtc) <= parseUtc(input.nowUtc)) {
    return { result: "expired", reason: "POLICY_MANIFEST_EXPIRED", evidenceRefs: [...sourceEvidenceIds, policy.packageId] };
  }
  return undefined;
}

function missionFreshness(input: SafetyEvaluationInput, sourceEvidenceIds: readonly string[]): FreshnessResult {
  const now = parseUtc(input.nowUtc);
  const snapshots = [...input.mission.dataSnapshots].sort((left, right) => compareStable(left.snapshotId, right.snapshotId));
  for (const snapshot of snapshots) {
    if (snapshot.status === "expired") return { result: "expired", reason: "MISSION_DATA_EXPIRED", evidenceRefs: [...sourceEvidenceIds, snapshot.snapshotId] };
    if (snapshot.status === "missing") return { result: "unknown", reason: "MISSION_DATA_MISSING", evidenceRefs: [...sourceEvidenceIds, snapshot.snapshotId] };
    if (snapshot.status === "conflicting") return { result: "unknown", reason: "MISSION_DATA_CONFLICTING", evidenceRefs: [...sourceEvidenceIds, snapshot.snapshotId] };
    if (snapshot.status === "unverified") return { result: "unknown", reason: "MISSION_DATA_UNVERIFIED", evidenceRefs: [...sourceEvidenceIds, snapshot.snapshotId] };
    const freshness = input.policy?.freshness[snapshot.kind];
    if (!freshness) return { result: "unknown", reason: "MISSION_DATA_FRESHNESS_POLICY_MISSING", evidenceRefs: [...sourceEvidenceIds, snapshot.snapshotId] };
    if (now - parseUtc(snapshot.capturedAtUtc) > freshness.maxAgeMinutes * 60_000) {
      return { result: "expired", reason: "MISSION_DATA_EXPIRED", evidenceRefs: [...sourceEvidenceIds, snapshot.snapshotId] };
    }
  }
  return undefined;
}

function evaluateRequirement(input: SafetyEvaluationInput, requirement: NormalizedRequirement): RuleEvaluation {
  const applicability = evaluateApplicability(input.mission, requirement, input.policy);
  const sourceEvidenceIds = evidenceIds(requirement);
  const freshness = applicability.result === "pass"
    ? policyFreshness(input, sourceEvidenceIds) ?? missionFreshness(input, sourceEvidenceIds)
    : undefined;
  return {
    requirementId: requirement.requirementId,
    result: freshness?.result ?? applicability.result,
    severity: requirement.severity,
    reason: freshness?.reason ?? applicability.reason,
    evidenceRefs: freshness?.evidenceRefs ?? sourceEvidenceIds,
    affectedGates: applicability.affectedGates,
  };
}

function conceptFor(evaluation: RuleEvaluation): ConceptId {
  if (evaluation.reason === "AUTONOMOUS_FLIGHT_PROHIBITED") return CONCEPT_IDS.autonomousFlightProhibited;
  if (evaluation.reason.includes("SUPERVISED_AUTOMATION")) return CONCEPT_IDS.supervisedAutomationEvidenceMissing;
  if (evaluation.reason.includes("IFR")) return CONCEPT_IDS.ifrEvidenceIncomplete;
  if (evaluation.reason === "APPROVED_POLICY_REQUIRED" || evaluation.reason.startsWith("POLICY_")) return CONCEPT_IDS.policyNotApproved;
  if (evaluation.result === "fail") return CONCEPT_IDS.requirementFailed;
  if (evaluation.result === "expired") return CONCEPT_IDS.requirementExpired;
  if (evaluation.result === "not-reviewed") return CONCEPT_IDS.requirementNotReviewed;
  return CONCEPT_IDS.requirementUnknown;
}

function blockerSeverity(evaluation: RuleEvaluation): SafetyBlocker["severity"] {
  if (evaluation.reason === "APPROVED_POLICY_REQUIRED" || evaluation.reason.startsWith("POLICY_")) return "policy";
  if (evaluation.result === "unknown" || evaluation.result === "expired") return "data";
  return "hard";
}

function blockerCode(result: RuleEvaluation["result"]): string {
  if (result === "fail") return "REQUIREMENT_FAILED";
  if (result === "expired") return "REQUIREMENT_EXPIRED";
  if (result === "not-reviewed") return "REQUIREMENT_NOT_REVIEWED";
  return "REQUIREMENT_UNKNOWN";
}

function requiresAction(evaluation: RuleEvaluation): boolean {
  return evaluation.result !== "pass" && evaluation.affectedGates.length > 0;
}

function blockerFor(evaluation: RuleEvaluation): SafetyBlocker {
  return {
    code: blockerCode(evaluation.result),
    conceptId: conceptFor(evaluation),
    severity: blockerSeverity(evaluation),
    explanationKey: evaluation.reason,
    evidenceRefs: evaluation.evidenceRefs,
  };
}

type FleetFactDomain = "fleet" | "capability" | "battery" | "maintenance" | "crew" | "energy";

const FLEET_GATES: Readonly<Record<FleetFactDomain, readonly GateName[]>> = {
  fleet: ["safety", "commander"],
  capability: ["safety", "commander"],
  battery: ["maintenance", "safety", "commander"],
  maintenance: ["maintenance", "safety", "commander"],
  crew: ["operator", "safety", "commander"],
  energy: ["safety", "commander"],
};

const FLEET_CODES: Readonly<Record<FleetFactDomain, { blocked: string; unknown: string; accepted: string }>> = {
  fleet: { blocked: "FLEET_CONFIGURATION_BLOCKED", unknown: "FLEET_FACTS_UNKNOWN", accepted: "FLEET_CONFIGURATION_ACCEPTED" },
  capability: { blocked: "CAPABILITY_NOT_APPROVED", unknown: "CAPABILITY_EVIDENCE_UNKNOWN", accepted: "CAPABILITY_EVIDENCE_ACCEPTED" },
  battery: { blocked: "BATTERY_NOT_RELEASED", unknown: "BATTERY_EVIDENCE_UNKNOWN", accepted: "BATTERY_EVIDENCE_ACCEPTED" },
  maintenance: { blocked: "MAINTENANCE_RELEASE_BLOCKED", unknown: "MAINTENANCE_EVIDENCE_UNKNOWN", accepted: "MAINTENANCE_EVIDENCE_ACCEPTED" },
  crew: { blocked: "CREW_QUALIFICATION_BLOCKED", unknown: "CREW_EVIDENCE_UNKNOWN", accepted: "CREW_EVIDENCE_ACCEPTED" },
  energy: { blocked: "INSUFFICIENT_RESERVE", unknown: "ENERGY_EVIDENCE_UNKNOWN", accepted: "ENERGY_RESERVE_ACCEPTED" },
};

interface FleetRuleResult {
  evaluation: RuleEvaluation;
  blocker?: SafetyBlocker;
}

function factEvidenceRefs(fact: FleetSafetyFact | FleetCrewFact | undefined): readonly string[] {
  if (fact?.evidenceRefs !== undefined) return fact.evidenceRefs;
  return fact?.evidenceRef === undefined ? [] : [fact.evidenceRef];
}

function fleetFactResult(
  requirementId: string,
  domain: FleetFactDomain,
  fact: FleetSafetyFact | FleetCrewFact | undefined,
): FleetRuleResult {
  const codes = FLEET_CODES[domain];
  const evidenceRefs = factEvidenceRefs(fact);
  const accepted = fact !== undefined && fact.status === "pass" && evidenceRefs.length > 0;
  const status = accepted ? "pass" : fact?.status === "blocked" ? "fail" : "unknown";
  const reason = accepted ? codes.accepted : status === "fail" ? codes.blocked : codes.unknown;
  const evaluation: RuleEvaluation = {
    requirementId,
    result: status,
    severity: "hard",
    reason,
    evidenceRefs,
    affectedGates: FLEET_GATES[domain],
  };
  if (status === "pass") return { evaluation };
  return {
    evaluation,
    blocker: {
      code: reason,
      conceptId: status === "fail" ? CONCEPT_IDS.requirementFailed : CONCEPT_IDS.requirementUnknown,
      severity: status === "fail" ? "hard" : "data",
      explanationKey: fact?.blockers?.[0] ?? reason,
      evidenceRefs,
    },
  };
}

function energyFactResult(requirementId: string, fact: FleetEnergyFact | undefined): FleetRuleResult {
  const reserveFieldsKnown = fact !== undefined
    && Number.isFinite(fact.recoveryPercent)
    && Number.isFinite(fact.diversionPercent)
    && Number.isFinite(fact.contingencyPercent);
  return fleetFactResult(
    requirementId,
    "energy",
    reserveFieldsKnown ? fact : fact === undefined ? undefined : { ...fact, status: "unknown", blockers: [...(fact.blockers ?? []), "ENERGY_RESERVE_FACTS_UNKNOWN"] },
  );
}

function factForAircraft(facts: readonly FleetSafetyFact[], aircraftId: string): FleetSafetyFact | undefined {
  return facts.find((fact) => fact.aircraftId === aircraftId);
}

function crewFactForAircraft(facts: FleetSafetyFacts, aircraftId: string): FleetCrewFact | undefined {
  const crewEvaluations = facts.crewEvaluations ?? [];
  const fact = crewEvaluations.find((item) => item.aircraftId === aircraftId)
    ?? (crewEvaluations.length === 1 && crewEvaluations[0]?.aircraftId === undefined ? crewEvaluations[0] : undefined);
  return fact;
}

function evaluateFleetFacts(mission: SafetyEvaluationInput["mission"], facts: FleetSafetyFacts): { evaluations: RuleEvaluation[]; blockers: SafetyBlocker[] } {
  const evaluations: RuleEvaluation[] = [];
  const blockers: SafetyBlocker[] = [];
  const multipleAircraft = mission.aircraft.length > 1;
  const requirementId = (base: string, aircraftId: string): string => multipleAircraft ? base + "." + aircraftId : base;
  const add = (result: FleetRuleResult): void => {
    evaluations.push(result.evaluation);
    if (result.blocker !== undefined) blockers.push(result.blocker);
  };

  for (const aircraft of mission.aircraft) {
    const aircraftId = aircraft.aircraftId;
    if (facts.fleet !== undefined) add(fleetFactResult(requirementId("fleet.configuration", aircraftId), "fleet", factForAircraft(facts.fleet, aircraftId)));
    if (facts.capability !== undefined) add(fleetFactResult(requirementId("fleet.capability", aircraftId), "capability", factForAircraft(facts.capability, aircraftId)));
    if (facts.battery !== undefined) add(fleetFactResult(requirementId("fleet.battery", aircraftId), "battery", factForAircraft(facts.battery, aircraftId)));
    add(fleetFactResult(requirementId("maintenance.release", aircraftId), "maintenance", factForAircraft(facts.maintenance, aircraftId)));
    if (facts.crewEvaluations !== undefined) add(fleetFactResult(requirementId("crew.qualification", aircraftId), "crew", crewFactForAircraft(facts, aircraftId)));
    add(energyFactResult(requirementId("energy.reserve", aircraftId), factForAircraft(facts.energy, aircraftId) as FleetEnergyFact | undefined));
  }
  return { evaluations, blockers };
}

function evaluationStatus(evaluations: readonly RuleEvaluation[], hardBlockers: readonly SafetyBlocker[]): SafetyEvaluationResult["status"] {
  if (hardBlockers.length > 0 || evaluations.some((evaluation) => requiresAction(evaluation) && evaluation.severity === "hard")) return "blocked";
  if (evaluations.some((evaluation) => requiresAction(evaluation) && evaluation.severity === "soft")) return "conditional";
  if (evaluations.some(requiresAction)) return "degraded";
  return "ready";
}

function invalidatedGates(evaluations: readonly RuleEvaluation[], hardBlockers: readonly SafetyBlocker[]): GateName[] {
  const gates = new Set<GateName>();
  if (hardBlockers.length > 0) for (const gate of HARD_BLOCKER_GATES) gates.add(gate);
  for (const evaluation of evaluations) {
    if (requiresAction(evaluation)) for (const gate of evaluation.affectedGates) gates.add(gate);
  }
  return GATE_ORDER.filter((gate) => gates.has(gate));
}

/** Evaluates a frozen mission revision without locale, I/O, or mutable state. */
export function evaluateMission(input: SafetyEvaluationInput): SafetyEvaluationResult {
  parseUtc(input.nowUtc);
  const requirementEvaluations = [...input.requirements]
    .sort((left, right) => compareStable(left.requirementId, right.requirementId))
    .map((requirement) => evaluateRequirement(input, requirement));
  const fleetResult = input.fleetSafetyFacts === undefined
    ? { evaluations: [], blockers: [] }
    : evaluateFleetFacts(input.mission, input.fleetSafetyFacts);
  const evaluations = [...requirementEvaluations, ...fleetResult.evaluations]
    .sort((left, right) => compareStable(left.requirementId, right.requirementId));
  const hardBlockers = [
    ...buildHardBlockers(input.mission, input.fleetSafetyFacts === undefined ? {} : { crew: input.fleetSafetyFacts.crew }),
    ...fleetResult.blockers,
  ];
  const ruleBlockers = requirementEvaluations.filter(requiresAction).map(blockerFor);
  return createSafetyEvaluationResult({
    missionRevisionId: input.mission.id,
    status: evaluationStatus(evaluations, hardBlockers),
    evaluations,
    blockers: [...hardBlockers, ...ruleBlockers],
    invalidatedGates: invalidatedGates(evaluations, hardBlockers),
    kernelVersion: KERNEL_VERSION,
  });
}

/** Renders controlled labels only; locale never affects the decision result. */
export function explainEvaluation(evaluation: SafetyEvaluationResult, locale: "es" | "en"): LocalizedExplanation {
  const conceptIds = [...new Set(evaluation.blockers.map((blocker) => blocker.conceptId))];
  for (const conceptId of conceptIds) {
    if (!(conceptId in CONCEPT_LABELS)) throw new RangeError(`unknown controlled concept ID: ${conceptId}`);
  }
  const labels = conceptIds.map((conceptId) => {
    const label = CONCEPT_LABELS[conceptId as ConceptId];
    return locale === "en" ? label.en ?? label.es : label.es;
  });
  return Object.freeze({
    locale,
    conceptIds: Object.freeze(conceptIds),
    labels: Object.freeze(labels),
    translationMissing: locale === "en" && conceptIds.some((conceptId) => CONCEPT_LABELS[conceptId as ConceptId].en === undefined),
  });
}
