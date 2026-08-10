export type ParticipantCode = string & { readonly __brand: "ParticipantCode" };

export interface ResearchSession {
  readonly id: string;
  readonly protocolId: string;
  readonly protocolVersion?: string;
  readonly ethicsApprovalId: string;
  readonly consentVersion?: string;
  readonly participantCode: ParticipantCode;
  readonly conditionAssignment: string;
  readonly startedAtUtc: string;
  readonly endedAtUtc?: string;
  readonly permittedSensors?: readonly string[];
  readonly nonDispatchable: true;
  readonly events: readonly ResearchEvent[];
}

export interface ResearchEvent {
  readonly eventId: string;
  readonly sessionId: string;
  readonly occurredAtUtc: string;
  readonly sequence: number;
  readonly type: string;
  readonly dataDomain: "research";
  readonly nonDispatchable: true;
  readonly payload: Record<string, unknown>;
  readonly quality: "valid" | "degraded" | "rejected";
}

export interface Protocol {
  readonly id: string;
  readonly version: string;
  readonly title: string;
  readonly investigatorId: string;
  readonly ethicsApprovalId: string;
  readonly permittedInstruments: readonly string[];
  readonly permittedSensors: readonly string[];
  readonly retentionDays: number;
  readonly status: "draft" | "approved" | "expired" | "closed";
  /** Human-readable statement of the variables collected by the protocol. */
  readonly dataMinimizationStatement?: string;
  /** Human-readable withdrawal and retention behavior approved for the protocol. */
  readonly withdrawalPolicy?: string;
}

export interface EthicsApproval {
  readonly id: string;
  readonly protocolId: string;
  readonly status: "current" | "expired" | "withdrawn";
  readonly approvedFromUtc: string;
  readonly expiresAtUtc: string;
}

export interface ConsentRecord {
  readonly id: string;
  readonly protocolId: string;
  readonly participantCode: ParticipantCode;
  readonly consentVersion: string;
  readonly consentedAtUtc: string;
  readonly withdrawnAtUtc?: string;
  readonly withdrawalReason?: string;
}

export interface ConditionAssignment { readonly sessionId: string; readonly conditionId: string; readonly assignedAtUtc: string; readonly randomizationBlock?: string }
export interface InstrumentDefinition { readonly id: string; readonly name: "SAGAT" | "NASA-TLX" | "ISA" | "Bedford" | "SART" | "custom"; readonly version: string; readonly responseSchema: Record<string, unknown>; readonly status: "approved-template" | "protocol-specific" | "retired" }
export interface InstrumentResponse { readonly sessionId: string; readonly instrumentId: string; readonly administeredAtUtc: string; readonly values: Record<string, number | string | null>; readonly missingReason?: string; readonly instrumentVersion?: string }
export interface AggregateReview {
  readonly id: string;
  readonly protocolIds: readonly string[];
  readonly minimumCellSize: number;
  readonly permittedUses: readonly ("training" | "interface-change" | "sms-assurance")[];
  readonly findings: readonly string[];
  readonly limitations: readonly string[];
  readonly reviewerId: string;
  readonly ethicsApprovalIds?: readonly string[];
  readonly analysisScope?: string;
  readonly approvedAtUtc?: string;
}
export interface ResearchAdapter { readonly adapterId: string; connect(session: ResearchSession, signal: AbortSignal): Promise<void>; readEvent(signal: AbortSignal): Promise<ResearchEvent | null>; close(): Promise<void> }

function isRecord(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === "object" && !Array.isArray(value); }
function requiredText(value: unknown, field: string): string { if (typeof value !== "string" || value.trim() === "") throw new TypeError(`${field} is required`); return value; }
function utc(value: unknown, field: string): string { const text = requiredText(value, field); if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(text) || !Number.isFinite(Date.parse(text))) throw new TypeError(`${field} must be UTC`); return text; }
function freeze<T>(value: T): T { if (value && typeof value === "object" && !Object.isFrozen(value)) { Object.freeze(value); for (const child of Object.values(value as Record<string, unknown>)) freeze(child); } return value; }
function strictKeys(value: Record<string, unknown>, allowed: readonly string[]): void { const unknown = Object.keys(value).find((key) => !allowed.includes(key)); if (unknown !== undefined) throw new TypeError(`separation boundary rejects field: ${unknown}`); }

export function parseResearchEvent(input: unknown): ResearchEvent {
  if (!isRecord(input)) throw new TypeError("research event must be an object");
  strictKeys(input, ["eventId", "sessionId", "occurredAtUtc", "sequence", "type", "dataDomain", "nonDispatchable", "payload", "quality"]);
  if (input.dataDomain !== "research") throw new TypeError("research event dataDomain is invalid");
  if (input.nonDispatchable !== true) throw new TypeError("research events are non-dispatchable");
  if (typeof input.sequence !== "number" || !Number.isInteger(input.sequence) || input.sequence < 0) throw new TypeError("sequence is invalid");
  if (!isRecord(input.payload)) throw new TypeError("payload must be an object");
  const quality = requiredText(input.quality, "quality");
  const qualities: readonly ResearchEvent["quality"][] = ["valid", "degraded", "rejected"];
  if (!qualities.includes(quality as ResearchEvent["quality"])) throw new TypeError("quality is invalid");
  return freeze({ eventId: requiredText(input.eventId, "eventId"), sessionId: requiredText(input.sessionId, "sessionId"), occurredAtUtc: utc(input.occurredAtUtc, "occurredAtUtc"), sequence: input.sequence, type: requiredText(input.type, "type"), dataDomain: "research" as const, nonDispatchable: true as const, payload: { ...input.payload }, quality: quality as ResearchEvent["quality"] });
}

export function parseResearchSession(input: unknown): ResearchSession {
  if (!isRecord(input)) throw new TypeError("research session must be an object");
  strictKeys(input, ["id", "protocolId", "protocolVersion", "ethicsApprovalId", "participantCode", "consentVersion", "conditionAssignment", "startedAtUtc", "endedAtUtc", "permittedSensors", "nonDispatchable", "events"]);
  if (input.nonDispatchable !== true) throw new TypeError("research sessions are non-dispatchable");
  const events = input.events;
  if (!Array.isArray(events)) throw new TypeError("events must be an array");
  const permittedSensors = input.permittedSensors === undefined ? undefined : input.permittedSensors;
  if (permittedSensors !== undefined && (!Array.isArray(permittedSensors) || permittedSensors.some((sensor) => typeof sensor !== "string" || sensor.trim() === ""))) throw new TypeError("permittedSensors is invalid");
  const protocolVersion = input.protocolVersion === undefined ? undefined : requiredText(input.protocolVersion, "protocolVersion");
  const consentVersion = input.consentVersion === undefined ? undefined : requiredText(input.consentVersion, "consentVersion");
  const session = { id: requiredText(input.id, "id"), protocolId: requiredText(input.protocolId, "protocolId"), ...(protocolVersion === undefined ? {} : { protocolVersion }), ethicsApprovalId: requiredText(input.ethicsApprovalId, "ethicsApprovalId"), ...(consentVersion === undefined ? {} : { consentVersion }), participantCode: requiredText(input.participantCode, "participantCode") as ParticipantCode, conditionAssignment: requiredText(input.conditionAssignment, "conditionAssignment"), startedAtUtc: utc(input.startedAtUtc, "startedAtUtc"), ...(input.endedAtUtc === undefined ? {} : { endedAtUtc: utc(input.endedAtUtc, "endedAtUtc") }), ...(permittedSensors === undefined ? {} : { permittedSensors: [...permittedSensors as string[]] }), nonDispatchable: true as const, events: events.map(parseResearchEvent) };
  return freeze(session);
}
