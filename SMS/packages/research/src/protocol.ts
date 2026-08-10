import {
  parseResearchSession,
  type ConditionAssignment,
  type ConsentRecord,
  type EthicsApproval,
  type ParticipantCode,
  type Protocol,
  type ResearchSession,
} from "./types.js";

export interface RegisterProtocolInput {
  readonly id: string;
  readonly version: string;
  readonly title: string;
  readonly investigatorId: string;
  readonly ethicsApprovalId: string;
  readonly permittedInstruments: readonly string[];
  readonly permittedSensors: readonly string[];
  readonly retentionDays: number;
  readonly status: Protocol["status"];
  readonly dataMinimizationStatement?: string;
  readonly withdrawalPolicy?: string;
}

export interface OpenConsentedSessionInput {
  readonly protocol: Protocol;
  readonly ethicsApproval: EthicsApproval;
  /** Raw input is accepted so the boundary can validate and brand the participant code. */
  readonly consent?: unknown;
  readonly participantCode: string;
  readonly conditionAssignment: string | ConditionAssignment;
  readonly startedAtUtc: string;
  readonly endedAtUtc?: string;
  readonly sessionId?: string;
}

const protocolStatuses: readonly Protocol["status"][] = ["draft", "approved", "expired", "closed"];
const ethicsStatuses: readonly EthicsApproval["status"][] = ["current", "expired", "withdrawn"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requiredText(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") throw new TypeError(`${field} is required`);
  return value.trim();
}

function utc(value: unknown, field: string): string {
  const text = requiredText(value, field);
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(text) || !Number.isFinite(Date.parse(text))) {
    throw new TypeError(`${field} must be UTC`);
  }
  return text;
}

function strictKeys(value: Record<string, unknown>, allowed: readonly string[]): void {
  const unknown = Object.keys(value).find((key) => !allowed.includes(key));
  if (unknown !== undefined) throw new TypeError(`research separation boundary rejects field: ${unknown}`);
}

function textArray(value: unknown, field: string): readonly string[] {
  if (!Array.isArray(value)) throw new TypeError(`${field} must be an array`);
  const result = value.map((item, index) => requiredText(item, `${field}[${index}]`));
  if (new Set(result).size !== result.length) throw new TypeError(`${field} must not contain duplicates`);
  return result;
}

function freeze<T>(value: T): T {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value as Record<string, unknown>)) freeze(child);
  }
  return value;
}

function parseEthicsApproval(input: unknown): EthicsApproval {
  if (!isRecord(input)) throw new TypeError("ethics approval is required");
  strictKeys(input, ["id", "protocolId", "status", "approvedFromUtc", "expiresAtUtc"]);
  const approvedFromUtc = utc(input.approvedFromUtc, "ethicsApproval.approvedFromUtc");
  const expiresAtUtc = utc(input.expiresAtUtc, "ethicsApproval.expiresAtUtc");
  if (Date.parse(expiresAtUtc) <= Date.parse(approvedFromUtc)) throw new TypeError("ethics approval expiry is invalid");
  const status = requiredText(input.status, "ethicsApproval.status") as EthicsApproval["status"];
  if (!ethicsStatuses.includes(status)) throw new TypeError("ethicsApproval.status is invalid");
  return freeze({
    id: requiredText(input.id, "ethicsApproval.id"),
    protocolId: requiredText(input.protocolId, "ethicsApproval.protocolId"),
    status,
    approvedFromUtc,
    expiresAtUtc,
  });
}

function parseConsent(input: unknown): ConsentRecord {
  if (!isRecord(input)) throw new TypeError("consent is required");
  strictKeys(input, ["id", "protocolId", "participantCode", "consentVersion", "consentedAtUtc", "withdrawnAtUtc", "withdrawalReason"]);
  const consentedAtUtc = utc(input.consentedAtUtc, "consent.consentedAtUtc");
  const withdrawnAtUtc = input.withdrawnAtUtc === undefined ? undefined : utc(input.withdrawnAtUtc, "consent.withdrawnAtUtc");
  if (withdrawnAtUtc !== undefined && Date.parse(withdrawnAtUtc) < Date.parse(consentedAtUtc)) {
    throw new TypeError("consent withdrawal cannot precede consent");
  }
  const withdrawalReason = input.withdrawalReason === undefined ? undefined : requiredText(input.withdrawalReason, "consent.withdrawalReason");
  return freeze({
    id: requiredText(input.id, "consent.id"),
    protocolId: requiredText(input.protocolId, "consent.protocolId"),
    participantCode: requiredText(input.participantCode, "consent.participantCode") as ParticipantCode,
    consentVersion: requiredText(input.consentVersion, "consent.consentVersion"),
    consentedAtUtc,
    ...(withdrawnAtUtc === undefined ? {} : { withdrawnAtUtc }),
    ...(withdrawalReason === undefined ? {} : { withdrawalReason }),
  });
}

export function registerProtocol(input: unknown): Protocol {
  if (!isRecord(input)) throw new TypeError("protocol must be an object");
  strictKeys(input, ["id", "version", "title", "investigatorId", "ethicsApprovalId", "permittedInstruments", "permittedSensors", "retentionDays", "status", "dataMinimizationStatement", "withdrawalPolicy"]);
  const status = requiredText(input.status, "status") as Protocol["status"];
  if (!protocolStatuses.includes(status)) throw new TypeError("status is invalid");
  if (!Number.isInteger(input.retentionDays) || (input.retentionDays as number) <= 0) throw new TypeError("retentionDays must be a positive integer");
  const dataMinimizationStatement = input.dataMinimizationStatement === undefined
    ? "Collect only pseudonymous participant, condition, instrument, sensor, timing, and quality fields required by the approved protocol."
    : requiredText(input.dataMinimizationStatement, "dataMinimizationStatement");
  const withdrawalPolicy = input.withdrawalPolicy === undefined
    ? "Record withdrawal and preserve audit provenance; apply approved retention and deletion controls without restoring operational identity."
    : requiredText(input.withdrawalPolicy, "withdrawalPolicy");
  return freeze({
    id: requiredText(input.id, "id"),
    version: requiredText(input.version, "version"),
    title: requiredText(input.title, "title"),
    investigatorId: requiredText(input.investigatorId, "investigatorId"),
    ethicsApprovalId: requiredText(input.ethicsApprovalId, "ethicsApprovalId"),
    permittedInstruments: textArray(input.permittedInstruments, "permittedInstruments"),
    permittedSensors: textArray(input.permittedSensors, "permittedSensors"),
    retentionDays: input.retentionDays as number,
    status,
    dataMinimizationStatement,
    withdrawalPolicy,
  });
}

export function openConsentedSession(input: OpenConsentedSessionInput): ResearchSession {
  if (!isRecord(input)) throw new TypeError("session input must be an object");
  strictKeys(input, ["protocol", "ethicsApproval", "consent", "participantCode", "conditionAssignment", "startedAtUtc", "endedAtUtc", "sessionId"]);
  if (!isRecord(input.protocol)) throw new TypeError("protocol is required");
  const protocol = input.protocol as Protocol;
  if (protocol.status !== "approved") throw new TypeError("protocol must be approved");
  const protocolId = requiredText(protocol.id, "protocol.id");
  const ethicsApproval = parseEthicsApproval(input.ethicsApproval);
  if (ethicsApproval.id !== requiredText(protocol.ethicsApprovalId, "protocol.ethicsApprovalId")) throw new TypeError("ethics approval does not match protocol");
  if (ethicsApproval.protocolId !== protocolId) throw new TypeError("ethics approval protocol does not match");
  if (ethicsApproval.status !== "current") throw new TypeError("current ethics approval is required");

  const startedAtUtc = utc(input.startedAtUtc, "startedAtUtc");
  const startedAt = Date.parse(startedAtUtc);
  if (startedAt < Date.parse(ethicsApproval.approvedFromUtc) || startedAt >= Date.parse(ethicsApproval.expiresAtUtc)) {
    throw new TypeError("session is outside the ethics approval window");
  }
  const endedAtUtc = input.endedAtUtc === undefined ? undefined : utc(input.endedAtUtc, "endedAtUtc");
  if (endedAtUtc !== undefined && Date.parse(endedAtUtc) < startedAt) throw new TypeError("endedAtUtc cannot precede startedAtUtc");

  const participantCode = requiredText(input.participantCode, "participantCode") as ParticipantCode;
  const consent = parseConsent(input.consent);
  if (consent.protocolId !== protocolId) throw new TypeError("consent does not match protocol");
  if (consent.participantCode !== participantCode) throw new TypeError("consent does not match participant");
  if (Date.parse(consent.consentedAtUtc) > startedAt) throw new TypeError("consent must precede session start");
  if (consent.withdrawnAtUtc !== undefined && Date.parse(consent.withdrawnAtUtc) <= startedAt) throw new TypeError("consent was withdrawn before session start");

  let conditionAssignment: string;
  if (typeof input.conditionAssignment === "string") {
    conditionAssignment = requiredText(input.conditionAssignment, "conditionAssignment");
  } else if (isRecord(input.conditionAssignment)) {
    strictKeys(input.conditionAssignment, ["sessionId", "conditionId", "assignedAtUtc", "randomizationBlock"]);
    conditionAssignment = requiredText(input.conditionAssignment.conditionId, "conditionAssignment.conditionId");
  } else {
    throw new TypeError("conditionAssignment is required");
  }

  const sessionId = input.sessionId === undefined ? `SESSION-${protocolId}-${startedAt}` : requiredText(input.sessionId, "sessionId");
  return parseResearchSession({
    id: sessionId,
    protocolId,
    protocolVersion: protocol.version,
    ethicsApprovalId: ethicsApproval.id,
    consentVersion: consent.consentVersion,
    participantCode,
    conditionAssignment,
    startedAtUtc,
    ...(endedAtUtc === undefined ? {} : { endedAtUtc }),
    permittedSensors: [...protocol.permittedSensors],
    nonDispatchable: true,
    events: [],
  });
}

export function assignCondition(sessionId: string, condition: string | { readonly conditionId: string; readonly assignedAtUtc?: string; readonly randomizationBlock?: string }): ConditionAssignment {
  const validSessionId = requiredText(sessionId, "sessionId");
  let conditionId: string;
  let assignedAtUtc: string | undefined;
  let randomizationBlock: string | undefined;
  if (typeof condition === "string") {
    conditionId = requiredText(condition, "conditionId");
  } else if (isRecord(condition)) {
    strictKeys(condition, ["conditionId", "assignedAtUtc", "randomizationBlock"]);
    conditionId = requiredText(condition.conditionId, "conditionId");
    assignedAtUtc = condition.assignedAtUtc === undefined ? undefined : utc(condition.assignedAtUtc, "assignedAtUtc");
    randomizationBlock = condition.randomizationBlock === undefined ? undefined : requiredText(condition.randomizationBlock, "randomizationBlock");
  } else {
    throw new TypeError("condition is required");
  }
  return freeze({
    sessionId: validSessionId,
    conditionId,
    assignedAtUtc: assignedAtUtc ?? new Date().toISOString(),
    ...(randomizationBlock === undefined ? {} : { randomizationBlock }),
  });
}
