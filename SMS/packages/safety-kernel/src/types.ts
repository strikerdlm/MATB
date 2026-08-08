import type { EvidenceReference, NormalizedRequirement, SignedPackageManifest } from "@fac-isr/evidence";
import { z } from "zod";

const id = z.string().trim().min(1);
const utc = z.string()
  .regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/, "timestamp must be UTC ISO-8601")
  .refine((value) => {
    const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/.exec(value);
    if (!match) return false;
    const [, year, month, day, hour, minute, second, fraction = ""] = match;
    const date = new Date(value);
    return Number.isFinite(date.getTime())
      && date.getUTCFullYear() === Number(year)
      && date.getUTCMonth() + 1 === Number(month)
      && date.getUTCDate() === Number(day)
      && date.getUTCHours() === Number(hour)
      && date.getUTCMinutes() === Number(minute)
      && date.getUTCSeconds() === Number(second)
      && date.getUTCMilliseconds() === Number(fraction.padEnd(3, "0") || 0);
  }, "timestamp must be a valid UTC instant");
const status = z.enum(["pass", "blocked", "unknown", "expired"]);

export type AircraftClass = "IA" | "IB" | "IC" | "II" | "III";
export type FlightRule = "VFR" | "IFR";
export type VisualCondition = "VLOS" | "EVLOS" | "BVLOS";
export type MissionState = "Draft" | "Planned" | "UnderReview" | "ReadyForRelease" | "Released" | "Active" | "Completed" | "Suspended" | "Aborted" | "PostFlightReview" | "Closed";
export type GateName = "maintenance" | "operator" | "safety" | "commander";
export type MaterialChangeField = "aircraft" | "gcs" | "payload" | "battery" | "software" | "crew" | "route" | "altitude" | "visual-condition" | "schedule" | "weather" | "notam" | "aip" | "risk" | "mitigation" | "exception" | "policy" | "evidence" | "display-note";

export interface AircraftAssignment { aircraftId: string; aircraftClass: AircraftClass; configuration: MissionRevision["configuration"]; operatorUserId?: string; maintenanceReleaseId?: string }
export interface CrewAssignment { userId: string; role: "operator" | "observer" | "maintainer" | "safety" | "commander"; aircraftId?: string; qualified: boolean; recencyCurrent: boolean; dutyStatus: "available" | "restricted" | "unavailable" | "unknown" }
export interface RouteSafetyFacts { areaId: string; routeHash: string; terrainStatus: z.infer<typeof status>; obstacleStatus: z.infer<typeof status>; airspaceStatus: z.infer<typeof status>; notamStatus: z.infer<typeof status>; visualConditionStatus: z.infer<typeof status> }
export interface DataSnapshotRef { snapshotId: string; kind: "aip" | "notam" | "weather" | "terrain" | "airspace" | "policy" | "regulation"; packageId: string; status: "current" | "expired" | "missing" | "conflicting" | "unverified"; capturedAtUtc: string }
export interface GroundControlStationFacts { gcsId: string; configurationHash: string }
export interface PayloadFacts { payloadId: string; configurationHash: string }
export interface BatteryFacts { batteryId: string; chemistry: "li-ion" | "li-po" | "other"; capacityWh: number; cycleCount: number }
export interface SoftwareBaseline { componentId: string; version: string; integrityHash: string }
export interface AltitudeProfile { minimumMetersAgl: number; maximumMetersAgl: number }
export interface MissionSchedule { plannedStartUtc: string; plannedEndUtc: string }
export type OperationalSnapshotKind = "weather" | "notam" | "aip";
export type OperationalDataSnapshot<K extends OperationalSnapshotKind> = DataSnapshotRef & { kind: K };
/** Explicit, unit-labelled minimum reserve facts. Unknown reserve fields are rejected. */
export interface ReserveFacts { recoveryPercent: number; diversionPercent: number; contingencyPercent: number }
export interface RiskAssessmentInput { hazardIds: readonly string[]; probability?: number; severity?: number; residualRiskBand?: string; acceptanceAuthorityId?: string; mitigationIds: readonly string[]; status: "draft" | "complete" | "blocked" | "accepted"; reserve?: ReserveFacts }
/** Input facts for an approved-matrix-only risk decision. Duration is in hours. */
export interface RiskEvaluationInput extends RiskAssessmentInput { policy: PolicyPackage | undefined; durationHours?: number }
export interface RiskEvaluation { status: "accepted" | "blocked"; band?: string; reason: string }
export interface FreshnessResult { status: "current" | "unknown" | "expired" | "blocked"; reason: string }
/** A revision-bound, explicit authorization for one stale or missing data source. */
export interface ControlledExceptionInput {
  missionRevisionId: string;
  sourceRevisionId: string;
  snapshot: DataSnapshotRef;
  alternateVerifiedSource?: DataSnapshotRef;
  consequence?: string;
  mitigation?: string;
  validityEndUtc?: string;
  safetyReview?: { reviewerId: string; approved: boolean };
  riskAuthorityId?: string;
  residualRiskBand?: string;
  operatorAcknowledged?: boolean;
}
export interface ExceptionResult { status: "accepted" | "blocked" | "expired"; reason: string }
export interface MissionRevision { id: string; missionId: string; revision: number; profileId: "fac-state-aviation" | "private-certified" | "civil-public"; state: MissionState; aircraft: readonly AircraftAssignment[]; gcs?: GroundControlStationFacts; payload?: PayloadFacts; battery?: BatteryFacts; software?: SoftwareBaseline; flightRule: FlightRule; visualCondition: VisualCondition; altitude?: AltitudeProfile; schedule?: MissionSchedule; configuration: "unarmed-isr" | "unarmed-support" | "armed" | "strike"; route: RouteSafetyFacts; crew: readonly CrewAssignment[]; evidenceSnapshotId: string; policyPackageId?: string; dataSnapshots: readonly DataSnapshotRef[]; riskAssessment: RiskAssessmentInput }
export interface RuleEvaluation { requirementId: string; result: "pass" | "fail" | "unknown" | "expired" | "not-reviewed"; severity: "hard" | "soft" | "advisory"; reason: string; evidenceRefs: readonly string[]; affectedGates: readonly GateName[] }
export interface SafetyBlocker { code: string; conceptId: string; severity: "hard" | "policy" | "data" | "authority"; explanationKey: string; evidenceRefs: readonly string[] }
export interface SafetyEvaluationResult { missionRevisionId: string; status: "ready" | "conditional" | "blocked" | "degraded"; evaluations: readonly RuleEvaluation[]; blockers: readonly SafetyBlocker[]; invalidatedGates: readonly GateName[]; kernelVersion: string }
export interface SafetyEvaluationInput { mission: MissionRevision; requirements: readonly NormalizedRequirement[]; policy: PolicyPackage | undefined; nowUtc: string }
export interface PolicyPackage { packageId: string; version: string; status: "draft" | "approved" | "expired" | "revoked"; riskMatrix?: { probabilityLevels: number; severityLevels: number; cells: readonly string[] }; nasoThresholds?: readonly { band: string; maxDurationHours?: number }[]; delegatedAuthorities: readonly { role: GateName; userRole: string; bands: readonly string[] }[]; freshness: Record<DataSnapshotRef["kind"], { maxAgeMinutes: number; critical: boolean }>; signature: string; manifest?: SignedPackageManifest }
export interface GateApproval { missionRevisionId: string; gate: GateName; decision: "accept" | "block" | "escalate"; valid: boolean }
export interface TransitionInput { missionRevisionId: string; current: MissionState; event: "plan" | "submit-review" | "gates-complete" | "release" | "activate" | "complete" | "suspend" | "abort" | "post-flight" | "close"; actor: { userId: string; role: CrewAssignment["role"] }; nowUtc: string; evaluation?: SafetyEvaluationResult; approvals?: readonly GateApproval[] }
export interface TransitionResult { state: MissionState; auditEvent: { type: string; missionRevisionId: string; actorUserId: string; occurredAtUtc: string } }
export interface DependencyGraphEntry { field: MaterialChangeField; affectedRequirementIds: readonly string[] }
export interface DependencyGraph { entries: readonly DependencyGraphEntry[] }
type MissionFieldChange<Field extends MaterialChangeField, Value> = { readonly field: Field; readonly previous: Value; readonly next: Value };
export type MissionRevisionChange =
  | MissionFieldChange<"aircraft", readonly AircraftAssignment[]>
  | MissionFieldChange<"gcs", GroundControlStationFacts | undefined>
  | MissionFieldChange<"payload", PayloadFacts | undefined>
  | MissionFieldChange<"battery", BatteryFacts | undefined>
  | MissionFieldChange<"software", SoftwareBaseline | undefined>
  | MissionFieldChange<"crew", readonly CrewAssignment[]>
  | MissionFieldChange<"route", RouteSafetyFacts>
  | MissionFieldChange<"altitude", AltitudeProfile | undefined>
  | MissionFieldChange<"visual-condition", VisualCondition>
  | MissionFieldChange<"schedule", MissionSchedule | undefined>
  | MissionFieldChange<"weather", OperationalDataSnapshot<"weather"> | undefined>
  | MissionFieldChange<"notam", OperationalDataSnapshot<"notam"> | undefined>
  | MissionFieldChange<"aip", OperationalDataSnapshot<"aip"> | undefined>
  | MissionFieldChange<"risk", RiskAssessmentInput>
  | MissionFieldChange<"mitigation", RiskAssessmentInput>
  | MissionFieldChange<"exception", RiskAssessmentInput>
  | MissionFieldChange<"policy", string | undefined>
  | MissionFieldChange<"evidence", string>
  | MissionFieldChange<"display-note", string>;
export type MaterialChangeInput = Readonly<{ dependencyGraph: DependencyGraph }> & MissionRevisionChange;
export interface InvalidationResult { material: boolean; affectedRequirementIds: readonly string[]; invalidatedGates: readonly GateName[]; reason: string }
export interface ApplicabilityResult { applicable: boolean; result: RuleEvaluation["result"]; reason: string; affectedGates: readonly GateName[] }
export interface FleetSafetyFacts { maintenance: readonly { aircraftId: string; status: "pass" | "blocked" | "unknown" }[]; crew: readonly CrewAssignment[]; energy: readonly { aircraftId: string; status: "pass" | "blocked" | "unknown"; evidenceRef: string }[] }
export interface GateEvaluationInput { mission: MissionRevision; evaluation: SafetyEvaluationResult; approvals: readonly GateApproval[]; nowUtc: string }
export interface FourGateResult { status: "ready" | "conditional" | "blocked"; gates: readonly { gate: GateName; status: "accepted" | "blocked" | "pending" | "invalid" }[]; blockers: readonly SafetyBlocker[] }
export interface LocalizedExplanation { locale: "es" | "en"; conceptIds: readonly string[]; labels: readonly string[]; translationMissing: boolean }

const AircraftSchema = z.object({ aircraftId: id, aircraftClass: z.enum(["IA", "IB", "IC", "II", "III"]), configuration: z.enum(["unarmed-isr", "unarmed-support", "armed", "strike"]), operatorUserId: id.optional(), maintenanceReleaseId: id.optional() }).strict();
const CrewSchema = z.object({ userId: id, role: z.enum(["operator", "observer", "maintainer", "safety", "commander"]), aircraftId: id.optional(), qualified: z.boolean(), recencyCurrent: z.boolean(), dutyStatus: z.enum(["available", "restricted", "unavailable", "unknown"]) }).strict();
const SnapshotSchema = z.object({ snapshotId: id, kind: z.enum(["aip", "notam", "weather", "terrain", "airspace", "policy", "regulation"]), packageId: id, status: z.enum(["current", "expired", "missing", "conflicting", "unverified"]), capturedAtUtc: utc }).strict();
const GroundControlStationSchema = z.object({ gcsId: id, configurationHash: id }).strict();
const PayloadSchema = z.object({ payloadId: id, configurationHash: id }).strict();
const BatterySchema = z.object({ batteryId: id, chemistry: z.enum(["li-ion", "li-po", "other"]), capacityWh: z.number().finite().positive(), cycleCount: z.number().int().nonnegative() }).strict();
const SoftwareSchema = z.object({ componentId: id, version: id, integrityHash: id }).strict();
const AltitudeSchema = z.object({ minimumMetersAgl: z.number().finite().nonnegative(), maximumMetersAgl: z.number().finite().nonnegative() }).strict().superRefine((value, ctx) => { if (value.maximumMetersAgl < value.minimumMetersAgl) ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["maximumMetersAgl"], message: "maximum altitude must be at least minimum altitude" }); });
const ScheduleSchema = z.object({ plannedStartUtc: utc, plannedEndUtc: utc }).strict().superRefine((value, ctx) => { if (Date.parse(value.plannedEndUtc) <= Date.parse(value.plannedStartUtc)) ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["plannedEndUtc"], message: "planned end must be after planned start" }); });
const ReserveSchema = z.object({ recoveryPercent: z.number().finite().min(0), diversionPercent: z.number().finite().min(0), contingencyPercent: z.number().finite().min(0) }).strict();
const RiskSchema = z.object({ hazardIds: z.array(id), probability: z.number().finite().min(0).max(1).optional(), severity: z.number().finite().min(0).optional(), residualRiskBand: id.optional(), acceptanceAuthorityId: id.optional(), mitigationIds: z.array(id), status: z.enum(["draft", "complete", "blocked", "accepted"]), reserve: ReserveSchema.optional() }).strict();
export const MissionRevisionSchema = z.object({ id, missionId: id, revision: z.number().int().nonnegative(), profileId: z.enum(["fac-state-aviation", "private-certified", "civil-public"]), state: z.enum(["Draft", "Planned", "UnderReview", "ReadyForRelease", "Released", "Active", "Completed", "Suspended", "Aborted", "PostFlightReview", "Closed"]), aircraft: z.array(AircraftSchema).min(1), gcs: GroundControlStationSchema.optional(), payload: PayloadSchema.optional(), battery: BatterySchema.optional(), software: SoftwareSchema.optional(), flightRule: z.enum(["VFR", "IFR"]), visualCondition: z.enum(["VLOS", "EVLOS", "BVLOS"]), altitude: AltitudeSchema.optional(), schedule: ScheduleSchema.optional(), configuration: z.enum(["unarmed-isr", "unarmed-support", "armed", "strike"]), route: z.object({ areaId: id, routeHash: id, terrainStatus: status, obstacleStatus: status, airspaceStatus: status, notamStatus: status, visualConditionStatus: status }).strict(), crew: z.array(CrewSchema), evidenceSnapshotId: id, policyPackageId: id.optional(), dataSnapshots: z.array(SnapshotSchema), riskAssessment: RiskSchema }).strict().superRefine((v, ctx) => { const ids = v.aircraft.map(a => a.aircraftId); if (new Set(ids).size !== ids.length) ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["aircraft"], message: "duplicate aircraft IDs" }); });

export const RuleEvaluationSchema = z.object({ requirementId: id, result: z.enum(["pass", "fail", "unknown", "expired", "not-reviewed"]), severity: z.enum(["hard", "soft", "advisory"]), reason: id, evidenceRefs: z.array(id), affectedGates: z.array(z.enum(["maintenance", "operator", "safety", "commander"])) }).strict();
export const SafetyBlockerSchema = z.object({ code: id, conceptId: id, severity: z.enum(["hard", "policy", "data", "authority"]), explanationKey: id, evidenceRefs: z.array(id) }).strict();
export const SafetyEvaluationResultSchema = z.object({ missionRevisionId: id, status: z.enum(["ready", "conditional", "blocked", "degraded"]), evaluations: z.array(RuleEvaluationSchema), blockers: z.array(SafetyBlockerSchema), invalidatedGates: z.array(z.enum(["maintenance", "operator", "safety", "commander"])), kernelVersion: z.string().regex(/^0\.\d+\.\d+$/) }).strict();
export const TransitionResultSchema = z.object({ state: z.enum(["Draft", "Planned", "UnderReview", "ReadyForRelease", "Released", "Active", "Completed", "Suspended", "Aborted", "PostFlightReview", "Closed"]), auditEvent: z.object({ type: id, missionRevisionId: id, actorUserId: id, occurredAtUtc: utc }).strict() }).strict();
export const InvalidationResultSchema = z.object({ material: z.boolean(), affectedRequirementIds: z.array(id), invalidatedGates: z.array(z.enum(["maintenance", "operator", "safety", "commander"])), reason: id }).strict();
function freeze<T>(value: T): T { if (value && typeof value === "object" && !Object.isFrozen(value)) { Object.freeze(value); for (const child of Object.values(value as Record<string, unknown>)) freeze(child); } return value; }
export function parseMissionRevision(input: unknown): MissionRevision { return freeze(MissionRevisionSchema.parse(input)); }
export function parseRuleEvaluation(input: unknown): RuleEvaluation { return freeze(RuleEvaluationSchema.parse(input)); }
export function parseSafetyBlocker(input: unknown): SafetyBlocker { return freeze(SafetyBlockerSchema.parse(input)); }
export function parseSafetyEvaluationResult(input: unknown): SafetyEvaluationResult { return freeze(SafetyEvaluationResultSchema.parse(input)); }
export function createSafetyEvaluationResult(input: SafetyEvaluationResult): SafetyEvaluationResult { return parseSafetyEvaluationResult(input); }
export function createTransitionResult(input: TransitionResult): TransitionResult { return freeze(TransitionResultSchema.parse(input)); }
export function createInvalidationResult(input: InvalidationResult): InvalidationResult { return freeze(InvalidationResultSchema.parse(input)); }
export function createRiskEvaluation(input: RiskEvaluation): RiskEvaluation { return freeze({ ...input }); }
export function createFreshnessResult(input: FreshnessResult): FreshnessResult { return freeze({ ...input }); }
export function createExceptionResult(input: ExceptionResult): ExceptionResult { return freeze({ ...input }); }
export type { EvidenceReference, NormalizedRequirement, SignedPackageManifest };
