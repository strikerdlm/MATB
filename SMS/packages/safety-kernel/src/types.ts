import type { EvidenceReference, NormalizedRequirement, SignedPackageManifest } from "@fac-isr/evidence";
import { z } from "zod";

const id = z.string().trim().min(1);
const utc = z.string().regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$/, "timestamp must be UTC ISO-8601");
const status = z.enum(["pass", "blocked", "unknown", "expired"]);

export type AircraftClass = "IA" | "IB" | "IC" | "II" | "III";
export type FlightRule = "VFR" | "IFR";
export type VisualCondition = "VLOS" | "EVLOS" | "BVLOS";
export type MissionState = "Draft" | "Planned" | "UnderReview" | "ReadyForRelease" | "Released" | "Active" | "Completed" | "Suspended" | "Aborted" | "PostFlightReview" | "Closed";
export type GateName = "maintenance" | "operator" | "safety" | "commander";

export interface AircraftAssignment { aircraftId: string; aircraftClass: AircraftClass; configuration: MissionRevision["configuration"]; operatorUserId?: string; maintenanceReleaseId?: string }
export interface CrewAssignment { userId: string; role: "operator" | "observer" | "maintainer" | "safety" | "commander"; aircraftId?: string; qualified: boolean; recencyCurrent: boolean; dutyStatus: "available" | "restricted" | "unavailable" | "unknown" }
export interface RouteSafetyFacts { areaId: string; routeHash: string; terrainStatus: z.infer<typeof status>; obstacleStatus: z.infer<typeof status>; airspaceStatus: z.infer<typeof status>; notamStatus: z.infer<typeof status>; visualConditionStatus: z.infer<typeof status> }
export interface DataSnapshotRef { snapshotId: string; kind: "aip" | "notam" | "weather" | "terrain" | "airspace" | "policy" | "regulation"; packageId: string; status: "current" | "expired" | "missing" | "conflicting" | "unverified"; capturedAtUtc: string }
export interface RiskAssessmentInput { hazardIds: readonly string[]; probability?: number; severity?: number; residualRiskBand?: string; acceptanceAuthorityId?: string; mitigationIds: readonly string[]; status: "draft" | "complete" | "blocked" | "accepted" }
export interface MissionRevision { id: string; missionId: string; revision: number; profileId: "fac-state-aviation" | "private-certified" | "civil-public"; state: MissionState; aircraft: readonly AircraftAssignment[]; flightRule: FlightRule; visualCondition: VisualCondition; configuration: "unarmed-isr" | "unarmed-support" | "armed" | "strike"; route: RouteSafetyFacts; crew: readonly CrewAssignment[]; evidenceSnapshotId: string; policyPackageId?: string; dataSnapshots: readonly DataSnapshotRef[]; riskAssessment: RiskAssessmentInput }
export interface RuleEvaluation { requirementId: string; result: "pass" | "fail" | "unknown" | "expired" | "not-reviewed"; severity: "hard" | "soft" | "advisory"; reason: string; evidenceRefs: readonly string[]; affectedGates: readonly GateName[] }
export interface SafetyBlocker { code: string; conceptId: string; severity: "hard" | "policy" | "data" | "authority"; explanationKey: string; evidenceRefs: readonly string[] }
export interface SafetyEvaluationResult { missionRevisionId: string; status: "ready" | "conditional" | "blocked" | "degraded"; evaluations: readonly RuleEvaluation[]; blockers: readonly SafetyBlocker[]; invalidatedGates: readonly GateName[]; kernelVersion: string }
export interface SafetyEvaluationInput { mission: MissionRevision; requirements: readonly NormalizedRequirement[]; policy: PolicyPackage | undefined; nowUtc: string }
export interface PolicyPackage { packageId: string; version: string; status: "draft" | "approved" | "expired" | "revoked"; riskMatrix?: { probabilityLevels: number; severityLevels: number; cells: readonly string[] }; nasoThresholds?: readonly { band: string; maxDurationHours?: number }[]; delegatedAuthorities: readonly { role: GateName; userRole: string; bands: readonly string[] }[]; freshness: Record<DataSnapshotRef["kind"], { maxAgeMinutes: number; critical: boolean }>; signature: string; manifest?: SignedPackageManifest }
export interface TransitionInput { current: MissionState; event: "plan" | "submit-review" | "gates-complete" | "release" | "activate" | "complete" | "suspend" | "abort" | "post-flight" | "close"; actor: { userId: string; role: CrewAssignment["role"] }; evaluation?: SafetyEvaluationResult }
export interface TransitionResult { state: MissionState; auditEvent: { type: string; actorUserId: string; occurredAtUtc: string } }
export interface MaterialChangeInput { mission: MissionRevision; field: string; previous: unknown; next: unknown }
export interface InvalidationResult { material: boolean; affectedRequirementIds: readonly string[]; invalidatedGates: readonly GateName[]; reason: string }
export interface GateEvaluationInput { mission: MissionRevision; evaluation: SafetyEvaluationResult; approvals: readonly { gate: GateName; decision: "accept" | "block" | "escalate"; valid: boolean }[]; nowUtc: string }
export interface FourGateResult { status: "ready" | "conditional" | "blocked"; gates: readonly { gate: GateName; status: "accepted" | "blocked" | "pending" | "invalid" }[]; blockers: readonly SafetyBlocker[] }

const AircraftSchema = z.object({ aircraftId: id, aircraftClass: z.enum(["IA", "IB", "IC", "II", "III"]), configuration: z.enum(["unarmed-isr", "unarmed-support", "armed", "strike"]), operatorUserId: id.optional(), maintenanceReleaseId: id.optional() }).strict();
const CrewSchema = z.object({ userId: id, role: z.enum(["operator", "observer", "maintainer", "safety", "commander"]), aircraftId: id.optional(), qualified: z.boolean(), recencyCurrent: z.boolean(), dutyStatus: z.enum(["available", "restricted", "unavailable", "unknown"]) }).strict();
const SnapshotSchema = z.object({ snapshotId: id, kind: z.enum(["aip", "notam", "weather", "terrain", "airspace", "policy", "regulation"]), packageId: id, status: z.enum(["current", "expired", "missing", "conflicting", "unverified"]), capturedAtUtc: utc }).strict();
const RiskSchema = z.object({ hazardIds: z.array(id), probability: z.number().finite().min(0).max(1).optional(), severity: z.number().finite().min(0).optional(), residualRiskBand: id.optional(), acceptanceAuthorityId: id.optional(), mitigationIds: z.array(id), status: z.enum(["draft", "complete", "blocked", "accepted"]) }).strict();
export const MissionRevisionSchema = z.object({ id, missionId: id, revision: z.number().int().nonnegative(), profileId: z.enum(["fac-state-aviation", "private-certified", "civil-public"]), state: z.enum(["Draft", "Planned", "UnderReview", "ReadyForRelease", "Released", "Active", "Completed", "Suspended", "Aborted", "PostFlightReview", "Closed"]), aircraft: z.array(AircraftSchema).min(1), flightRule: z.enum(["VFR", "IFR"]), visualCondition: z.enum(["VLOS", "EVLOS", "BVLOS"]), configuration: z.enum(["unarmed-isr", "unarmed-support", "armed", "strike"]), route: z.object({ areaId: id, routeHash: id, terrainStatus: status, obstacleStatus: status, airspaceStatus: status, notamStatus: status, visualConditionStatus: status }).strict(), crew: z.array(CrewSchema), evidenceSnapshotId: id, policyPackageId: id.optional(), dataSnapshots: z.array(SnapshotSchema), riskAssessment: RiskSchema }).strict().superRefine((v, ctx) => { const ids = v.aircraft.map(a => a.aircraftId); if (new Set(ids).size !== ids.length) ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["aircraft"], message: "duplicate aircraft IDs" }); });

export const RuleEvaluationSchema = z.object({ requirementId: id, result: z.enum(["pass", "fail", "unknown", "expired", "not-reviewed"]), severity: z.enum(["hard", "soft", "advisory"]), reason: id, evidenceRefs: z.array(id), affectedGates: z.array(z.enum(["maintenance", "operator", "safety", "commander"])) }).strict();
export const SafetyBlockerSchema = z.object({ code: id, conceptId: id, severity: z.enum(["hard", "policy", "data", "authority"]), explanationKey: id, evidenceRefs: z.array(id) }).strict();
export const SafetyEvaluationResultSchema = z.object({ missionRevisionId: id, status: z.enum(["ready", "conditional", "blocked", "degraded"]), evaluations: z.array(RuleEvaluationSchema), blockers: z.array(SafetyBlockerSchema), invalidatedGates: z.array(z.enum(["maintenance", "operator", "safety", "commander"])), kernelVersion: z.string().regex(/^0\.\d+\.\d+$/) }).strict();
function freeze<T>(value: T): T { if (value && typeof value === "object" && !Object.isFrozen(value)) { Object.freeze(value); for (const child of Object.values(value as Record<string, unknown>)) freeze(child); } return value; }
export function parseMissionRevision(input: unknown): MissionRevision { return freeze(MissionRevisionSchema.parse(input)); }
export function parseRuleEvaluation(input: unknown): RuleEvaluation { return freeze(RuleEvaluationSchema.parse(input)); }
export function parseSafetyBlocker(input: unknown): SafetyBlocker { return freeze(SafetyBlockerSchema.parse(input)); }
export function parseSafetyEvaluationResult(input: unknown): SafetyEvaluationResult { return freeze(SafetyEvaluationResultSchema.parse(input)); }
export function createSafetyEvaluationResult(input: SafetyEvaluationResult): SafetyEvaluationResult { return parseSafetyEvaluationResult(input); }
export type { EvidenceReference, NormalizedRequirement, SignedPackageManifest };
