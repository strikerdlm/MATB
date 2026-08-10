import { parseResearchEvent, type ResearchAdapter, type ResearchEvent, type ResearchSession } from "./types.js";

export interface MatbInputEvent {
  readonly eventId?: string;
  readonly sessionId?: string;
  readonly occurredAtUtc?: string;
  /** Milliseconds since Unix epoch, accepted for local MATB bridge records. */
  readonly timestamp?: number;
  readonly sequence?: number;
  readonly type: string;
  readonly payload: Record<string, unknown>;
  readonly quality?: ResearchEvent["quality"];
  readonly metadata?: Record<string, unknown>;
}

export interface MatbAdapterOptions {
  readonly adapterId?: string;
  readonly events?: readonly MatbInputEvent[];
  readonly permittedSensors?: readonly string[];
}

const forbiddenPayloadKeys = new Set(["operationalUserId", "userId", "operatorId", "personnelNumber", "callSign", "qualificationStatus", "releaseEligibility"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requiredText(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") throw new TypeError(`${field} is required`);
  return value.trim();
}

function normalizeUtc(value: unknown, field: string): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    const timestamp = new Date(value);
    if (Number.isFinite(timestamp.getTime())) return timestamp.toISOString();
  }
  const text = requiredText(value, field);
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(text) || !Number.isFinite(Date.parse(text))) throw new TypeError(`${field} must be UTC`);
  return text;
}

function strictKeys(value: Record<string, unknown>, allowed: readonly string[]): void {
  const unknown = Object.keys(value).find((key) => !allowed.includes(key));
  if (unknown !== undefined) throw new TypeError(`research adapter rejects field: ${unknown}`);
}

function rejectOperationalKeys(value: unknown, path = "payload"): void {
  if (!isRecord(value)) return;
  for (const [key, child] of Object.entries(value)) {
    if (forbiddenPayloadKeys.has(key)) throw new TypeError(`research separation boundary rejects ${path}.${key}`);
    rejectOperationalKeys(child, `${path}.${key}`);
  }
}

function clonePayload(raw: MatbInputEvent): Record<string, unknown> {
  if (!isRecord(raw.payload)) throw new TypeError("payload must be an object");
  rejectOperationalKeys(raw.payload);
  if (raw.metadata !== undefined) {
    if (!isRecord(raw.metadata)) throw new TypeError("metadata must be an object");
    rejectOperationalKeys(raw.metadata, "metadata");
  }
  return {
    ...raw.payload,
    ...(raw.metadata === undefined ? {} : { metadata: { ...raw.metadata } }),
  };
}

function abortIfRequested(signal: AbortSignal): void {
  if (signal.aborted) throw new Error("research adapter operation aborted");
}

function optionsFrom(eventsOrOptions: readonly MatbInputEvent[] | MatbAdapterOptions): MatbAdapterOptions {
  return Array.isArray(eventsOrOptions) ? { events: eventsOrOptions as readonly MatbInputEvent[] } : eventsOrOptions as MatbAdapterOptions;
}

/**
 * Local, deterministic MATB bridge. It has no operational repository handles
 * and emits only the research event contract.
 */
export class MatbResearchAdapter implements ResearchAdapter {
  public readonly adapterId: string;
  private readonly sourceEvents: readonly MatbInputEvent[];
  private readonly permittedSensors?: readonly string[];
  private session?: ResearchSession;
  private cursor = 0;
  private connected = false;

  public constructor(eventsOrOptions: readonly MatbInputEvent[] | MatbAdapterOptions = []) {
    const options = optionsFrom(eventsOrOptions);
    this.adapterId = requiredText(options.adapterId ?? "matb-local-v1", "adapterId");
    this.sourceEvents = [...(options.events ?? [])];
    this.permittedSensors = options.permittedSensors === undefined ? undefined : [...options.permittedSensors];
  }

  public async connect(session: ResearchSession, signal: AbortSignal): Promise<void> {
    abortIfRequested(signal);
    if (!isRecord(session) || session.nonDispatchable !== true) throw new TypeError("MATB adapter requires a non-dispatchable research session");
    if (this.permittedSensors !== undefined && !this.permittedSensors.includes("matb")) throw new Error("MATB sensor is outside the approved scope");
    for (const raw of this.sourceEvents) {
      if (!isRecord(raw)) throw new TypeError("MATB event must be an object");
      strictKeys(raw, ["eventId", "sessionId", "occurredAtUtc", "timestamp", "sequence", "type", "payload", "quality", "metadata"]);
      if (raw.sessionId !== undefined && raw.sessionId !== session.id) throw new Error("MATB event session does not match connected session");
    }
    this.session = session;
    this.cursor = 0;
    this.connected = true;
  }

  public async readEvent(signal: AbortSignal): Promise<ResearchEvent | null> {
    abortIfRequested(signal);
    if (!this.connected || this.session === undefined) throw new Error("MATB adapter is not connected");
    const raw = this.sourceEvents[this.cursor];
    if (raw === undefined) return null;
    const sequence = raw.sequence ?? this.cursor;
    if (!Number.isInteger(sequence) || sequence < 0) throw new TypeError("MATB event sequence is invalid");
    const occurredAtUtc = raw.occurredAtUtc === undefined
      ? normalizeUtc(raw.timestamp, "timestamp")
      : normalizeUtc(raw.occurredAtUtc, "occurredAtUtc");
    const eventTime = Date.parse(occurredAtUtc);
    const start = Date.parse(this.session.startedAtUtc);
    const end = this.session.endedAtUtc === undefined ? Number.POSITIVE_INFINITY : Date.parse(this.session.endedAtUtc);
    if (eventTime < start || eventTime > end) throw new Error("MATB event is outside the connected session window");
    const event = parseResearchEvent({
      eventId: raw.eventId === undefined ? `${this.adapterId}:${this.session.id}:${sequence}` : requiredText(raw.eventId, "eventId"),
      sessionId: this.session.id,
      occurredAtUtc,
      sequence,
      type: (raw.type.startsWith("matb.") ? raw.type : `matb.${requiredText(raw.type, "type")}`),
      dataDomain: "research",
      nonDispatchable: true,
      payload: clonePayload(raw),
      quality: raw.quality ?? "valid",
    });
    this.cursor += 1;
    return event;
  }

  public async close(): Promise<void> {
    this.connected = false;
    this.session = undefined;
    this.cursor = 0;
  }
}

export function createMatbAdapter(eventsOrOptions: readonly MatbInputEvent[] | MatbAdapterOptions = []): MatbResearchAdapter {
  return new MatbResearchAdapter(eventsOrOptions);
}
