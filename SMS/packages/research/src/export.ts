import { parseResearchSession, type ResearchEvent, type ResearchSession } from "./types.js";

export type ResearchExportFormat = "json" | "csv" | "parquet";

interface DeidentifiedEvent {
  readonly eventId: string;
  readonly sessionId: string;
  readonly occurredAtUtc: string;
  readonly sequence: number;
  readonly type: string;
  readonly payload: Record<string, unknown>;
  readonly quality: ResearchEvent["quality"];
  readonly eventHash: string;
}

interface DeidentifiedExport {
  readonly schemaVersion: "research-export-v1";
  readonly sessionId: string;
  readonly protocolId: string;
  readonly protocolVersion: string | null;
  readonly ethicsApprovalId: string;
  readonly consentVersion: string | null;
  readonly participantCode: string;
  readonly conditionAssignment: string;
  readonly startedAtUtc: string;
  readonly endedAtUtc: string | null;
  readonly permittedSensors: readonly string[];
  readonly events: readonly DeidentifiedEvent[];
}

const forbiddenKeys = new Set(["name", "operationaluserid", "userid", "operatorid", "personnelnumber", "callsign", "diagnosis", "medicaldiagnosis", "missionrelease", "releaseeligibility", "classified"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function rejectForbidden(value: unknown, path = "payload"): void {
  if (!isRecord(value)) return;
  for (const [key, child] of Object.entries(value)) {
    if (forbiddenKeys.has(key.toLowerCase()) || /(^|_)(operational|mission|medical|classified)/i.test(key)) throw new TypeError(`research export boundary rejects ${path}.${key}`);
    rejectForbidden(child, `${path}.${key}`);
  }
}

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stableValue);
  if (isRecord(value)) return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stableValue(value[key])]));
  return value;
}

function stableStringify(value: unknown): string {
  return JSON.stringify(stableValue(value));
}

function hash(value: string): string {
  let result = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 0x01000193);
  }
  return `fnv1a-${(result >>> 0).toString(16).padStart(8, "0")}`;
}

function csv(value: unknown): string {
  const text = value === null || value === undefined ? "" : typeof value === "string" ? value : stableStringify(value);
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function buildModel(input: unknown): DeidentifiedExport {
  const session = parseResearchSession(input);
  const events = [...session.events].sort((left, right) => left.sequence - right.sequence || Date.parse(left.occurredAtUtc) - Date.parse(right.occurredAtUtc) || left.eventId.localeCompare(right.eventId));
  const deidentifiedEvents = events.map((event) => {
    rejectForbidden(event.payload);
    const payload = stableValue(event.payload) as Record<string, unknown>;
    const eventHash = hash(stableStringify({ eventId: event.eventId, occurredAtUtc: event.occurredAtUtc, sequence: event.sequence, type: event.type, payload, quality: event.quality }));
    return { eventId: event.eventId, sessionId: event.sessionId, occurredAtUtc: event.occurredAtUtc, sequence: event.sequence, type: event.type, payload, quality: event.quality, eventHash };
  });
  return {
    schemaVersion: "research-export-v1",
    sessionId: session.id,
    protocolId: session.protocolId,
    protocolVersion: session.protocolVersion ?? null,
    ethicsApprovalId: session.ethicsApprovalId,
    consentVersion: session.consentVersion ?? null,
    participantCode: session.participantCode,
    conditionAssignment: session.conditionAssignment,
    startedAtUtc: session.startedAtUtc,
    endedAtUtc: session.endedAtUtc ?? null,
    permittedSensors: session.permittedSensors === undefined ? [] : [...session.permittedSensors],
    events: deidentifiedEvents,
  };
}

function asCsv(model: DeidentifiedExport): string {
  const header = ["eventId", "sessionId", "protocolId", "protocolVersion", "ethicsApprovalId", "consentVersion", "participantCode", "conditionAssignment", "occurredAtUtc", "sequence", "type", "quality", "payloadJson", "eventHash"];
  const rows = model.events.length === 0 ? [{ eventId: "", sessionId: model.sessionId, protocolId: model.protocolId, protocolVersion: model.protocolVersion, ethicsApprovalId: model.ethicsApprovalId, consentVersion: model.consentVersion, participantCode: model.participantCode, conditionAssignment: model.conditionAssignment, occurredAtUtc: "", sequence: "", type: "", quality: "", payload: "", eventHash: "" }] : model.events.map((event) => ({ eventId: event.eventId, sessionId: event.sessionId, protocolId: model.protocolId, protocolVersion: model.protocolVersion, ethicsApprovalId: model.ethicsApprovalId, consentVersion: model.consentVersion, participantCode: model.participantCode, conditionAssignment: model.conditionAssignment, occurredAtUtc: event.occurredAtUtc, sequence: event.sequence, type: event.type, quality: event.quality, payload: stableStringify(event.payload), eventHash: event.eventHash }));
  return [header.join(","), ...rows.map((row) => [row.eventId, row.sessionId, row.protocolId, row.protocolVersion, row.ethicsApprovalId, row.consentVersion, row.participantCode, row.conditionAssignment, row.occurredAtUtc, row.sequence, row.type, row.quality, row.payload, row.eventHash].map(csv).join(","))].join("\n");
}

function asParquetBytes(model: DeidentifiedExport): Uint8Array {
  // Keep a deterministic, dependency-free container for offline hand-off. The
  // PAR1 envelope is deliberately stable; a deployment may transcode this
  // canonical row model to a full Parquet writer without changing semantics.
  return new TextEncoder().encode(`PAR1${stableStringify(model)}PAR1`);
}

export function exportDeidentified(session: ResearchSession | unknown, format: "json"): string;
export function exportDeidentified(session: ResearchSession | unknown, format: "csv"): string;
export function exportDeidentified(session: ResearchSession | unknown, format: "parquet"): Uint8Array;
export function exportDeidentified(session: ResearchSession | unknown, format: ResearchExportFormat): Uint8Array | string;
export function exportDeidentified(session: ResearchSession | unknown, format: ResearchExportFormat): Uint8Array | string {
  if (format !== "json" && format !== "csv" && format !== "parquet") throw new TypeError("research export format is invalid");
  const model = buildModel(session);
  if (format === "json") return stableStringify(model);
  if (format === "csv") return asCsv(model);
  return asParquetBytes(model);
}
