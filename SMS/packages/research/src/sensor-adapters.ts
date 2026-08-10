import { parseResearchEvent, type ResearchAdapter, type ResearchEvent, type ResearchSession } from "./types.js";

export type ResearchSensorKind = "hrv" | "eye-tracking" | "psychomotor";

export interface SensorInputEvent {
  readonly eventId?: string;
  readonly sessionId?: string;
  readonly occurredAtUtc?: string;
  readonly timestamp?: number;
  readonly sequence?: number;
  readonly type: string;
  readonly payload: Record<string, unknown>;
  readonly quality?: ResearchEvent["quality"];
  readonly metadata?: Record<string, unknown>;
}

export interface SensorAdapterOptions {
  readonly sensor: ResearchSensorKind;
  readonly adapterId?: string;
  readonly deviceId?: string;
  readonly events?: readonly SensorInputEvent[];
  readonly permittedSensors?: readonly string[];
}

const sensorKinds: readonly ResearchSensorKind[] = ["hrv", "eye-tracking", "psychomotor"];
const forbiddenKeys = new Set(["operationalUserId", "userId", "operatorId", "personnelNumber", "callSign", "qualificationStatus", "releaseEligibility"]);

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
    if (forbiddenKeys.has(key)) throw new TypeError(`research separation boundary rejects ${path}.${key}`);
    rejectOperationalKeys(child, `${path}.${key}`);
  }
}

function abortIfRequested(signal: AbortSignal): void {
  if (signal.aborted) throw new Error("research adapter operation aborted");
}

/**
 * Normalizes optional HRV, eye-tracking, and psychomotor streams into the same
 * research-only event contract. It intentionally has no operational store
 * dependency or command method.
 */
export class ResearchSensorAdapter implements ResearchAdapter {
  public readonly adapterId: string;
  public readonly sensor: ResearchSensorKind;
  private readonly deviceId?: string;
  private readonly sourceEvents: readonly SensorInputEvent[];
  private readonly configuredPermittedSensors?: readonly string[];
  private session?: ResearchSession;
  private cursor = 0;
  private connected = false;

  public constructor(options: SensorAdapterOptions) {
    if (!sensorKinds.includes(options.sensor)) throw new TypeError("sensor is not supported");
    this.sensor = options.sensor;
    this.adapterId = requiredText(options.adapterId ?? `${options.sensor}-local-v1`, "adapterId");
    this.deviceId = options.deviceId === undefined ? undefined : requiredText(options.deviceId, "deviceId");
    this.sourceEvents = [...(options.events ?? [])];
    this.configuredPermittedSensors = options.permittedSensors === undefined ? undefined : [...options.permittedSensors];
  }

  public async connect(session: ResearchSession, signal: AbortSignal): Promise<void> {
    abortIfRequested(signal);
    if (!isRecord(session) || session.nonDispatchable !== true) throw new TypeError("sensor adapter requires a non-dispatchable research session");
    if (session.permittedSensors !== undefined && !session.permittedSensors.includes(this.sensor)) throw new Error(`${this.sensor} sensor is outside the approved scope`);
    if (this.configuredPermittedSensors !== undefined && !this.configuredPermittedSensors.includes(this.sensor)) throw new Error(`${this.sensor} sensor is outside the approved scope`);
    for (const raw of this.sourceEvents) {
      if (!isRecord(raw)) throw new TypeError("sensor event must be an object");
      strictKeys(raw, ["eventId", "sessionId", "occurredAtUtc", "timestamp", "sequence", "type", "payload", "quality", "metadata"]);
      if (raw.sessionId !== undefined && raw.sessionId !== session.id) throw new Error("sensor event session does not match connected session");
    }
    this.session = session;
    this.cursor = 0;
    this.connected = true;
  }

  public async readEvent(signal: AbortSignal): Promise<ResearchEvent | null> {
    abortIfRequested(signal);
    if (!this.connected || this.session === undefined) throw new Error("sensor adapter is not connected");
    const raw = this.sourceEvents[this.cursor];
    if (raw === undefined) return null;
    const sequence = raw.sequence ?? this.cursor;
    if (!Number.isInteger(sequence) || sequence < 0) throw new TypeError("sensor event sequence is invalid");
    const occurredAtUtc = raw.occurredAtUtc === undefined ? normalizeUtc(raw.timestamp, "timestamp") : normalizeUtc(raw.occurredAtUtc, "occurredAtUtc");
    const eventTime = Date.parse(occurredAtUtc);
    const start = Date.parse(this.session.startedAtUtc);
    const end = this.session.endedAtUtc === undefined ? Number.POSITIVE_INFINITY : Date.parse(this.session.endedAtUtc);
    if (eventTime < start || eventTime > end) throw new Error("sensor event is outside the connected session window");
    if (!isRecord(raw.payload)) throw new TypeError("payload must be an object");
    rejectOperationalKeys(raw.payload);
    if (raw.metadata !== undefined) {
      if (!isRecord(raw.metadata)) throw new TypeError("metadata must be an object");
      rejectOperationalKeys(raw.metadata, "metadata");
    }
    const rawType = requiredText(raw.type, "type");
    if (rawType.includes(".") && !rawType.startsWith(`${this.sensor}.`)) throw new TypeError("sensor event type does not match adapter");
    const event = parseResearchEvent({
      eventId: raw.eventId === undefined ? `${this.adapterId}:${this.session.id}:${sequence}` : requiredText(raw.eventId, "eventId"),
      sessionId: this.session.id,
      occurredAtUtc,
      sequence,
      type: rawType.startsWith(`${this.sensor}.`) ? rawType : `${this.sensor}.${rawType}`,
      dataDomain: "research",
      nonDispatchable: true,
      payload: {
        sensor: this.sensor,
        ...(this.deviceId === undefined ? {} : { deviceId: this.deviceId }),
        ...raw.payload,
        ...(raw.metadata === undefined ? {} : { metadata: { ...raw.metadata } }),
      },
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

export function createSensorAdapter(options: SensorAdapterOptions): ResearchSensorAdapter {
  return new ResearchSensorAdapter(options);
}
