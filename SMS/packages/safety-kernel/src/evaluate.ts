import type { NormalizedRequirement } from "@fac-isr/evidence";
import { buildHardBlockers, evaluateApplicability } from "./applicability.js";
import { CONCEPT_IDS, CONCEPT_LABELS, type ConceptId } from "./terminology.js";
import { createSafetyEvaluationResult, type GateName, type LocalizedExplanation, type RuleEvaluation, type SafetyBlocker, type SafetyEvaluationInput, type SafetyEvaluationResult } from "./types.js";

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
  const policyResult = applicability.applicable ? policyFreshness(input, sourceEvidenceIds) : undefined;
  const freshness = policyResult ?? (applicability.result === "pass" ? missionFreshness(input, sourceEvidenceIds) : undefined);
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
  const evaluations = [...input.requirements]
    .sort((left, right) => compareStable(left.requirementId, right.requirementId))
    .map((requirement) => evaluateRequirement(input, requirement));
  const hardBlockers = buildHardBlockers(input.mission);
  const ruleBlockers = evaluations.filter(requiresAction).map(blockerFor);
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
