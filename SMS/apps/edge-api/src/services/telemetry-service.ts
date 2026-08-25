import { canonicalJson } from "@fac-isr/evidence";
import { canonicalizeTelemetry, TelemetryValidationError, type CanonicalTelemetry } from "@fac-isr/telemetry";
import type { TelemetryAdapterCertificate } from "../config.js";
import type { TelemetrySequenceRepository } from "../db/telemetry-sequence-repository.js";

const MAX_EVENT_BYTES = 16 * 1024;
const MAX_RETAINED_EVENTS = 1_000;
const MAX_TEXT_LENGTH = 256;

export class TelemetryServiceError extends Error {
  public constructor(public readonly statusCode: number, public readonly code: string, message: string) {
    super(message);
    this.name = "TelemetryServiceError";
  }
}

export interface TelemetryPeerIdentity {
  readonly authorized: boolean;
  readonly fingerprintSha256?: string;
  readonly subject?: string;
}

export interface TelemetryIngestionResult {
  readonly adapterId: string;
  readonly revisionId: string;
  readonly sequence: number;
  readonly status: "accepted";
  readonly event: CanonicalTelemetry;
}

interface TelemetryEnvelope {
  readonly revisionId: string;
  readonly sequence: number;
  readonly event: CanonicalTelemetry;
}

interface Subscriber {
  readonly push: (record: TelemetryIngestionResult) => boolean;
  readonly close: () => void;
}

export class TelemetryService {
  private readonly adapters: ReadonlyMap<string, TelemetryAdapterCertificate>;
  private readonly streams = new Map<string, TelemetryIngestionResult[]>();
  private readonly subscribers = new Map<string, Set<Subscriber>>();

  public constructor(adapters: readonly TelemetryAdapterCertificate[], private readonly sequenceRepository: TelemetrySequenceRepository) {
    this.adapters = new Map(adapters.map((record) => [record.fingerprintSha256, record]));
  }

  public authorizePeer(peer: TelemetryPeerIdentity): TelemetryAdapterCertificate {
    if (!peer.authorized || peer.fingerprintSha256 === undefined) throw new TelemetryServiceError(401, "CLIENT_CERTIFICATE_REQUIRED", "a verified client certificate is required");
    const fingerprint = peer.fingerprintSha256.replaceAll(":", "").toLowerCase();
    const adapter = this.adapters.get(fingerprint);
    if (adapter === undefined) throw new TelemetryServiceError(403, "TELEMETRY_ADAPTER_FORBIDDEN", "the client certificate is not allowlisted for telemetry ingestion");
    return adapter;
  }

  public ingest(input: unknown, peer: TelemetryPeerIdentity, missionAircraftIds?: readonly string[]): TelemetryIngestionResult {
    const adapter = this.authorizePeer(peer);
    const envelope = parseEnvelope(input);
    if (!adapter.aircraftIds.includes(envelope.event.aircraftId)) throw new TelemetryServiceError(403, "TELEMETRY_AIRCRAFT_FORBIDDEN", "the certificate is not assigned to this aircraft");
    if (missionAircraftIds !== undefined && !missionAircraftIds.includes(envelope.event.aircraftId)) throw new TelemetryServiceError(403, "TELEMETRY_MISSION_AIRCRAFT_FORBIDDEN", "the aircraft is not assigned to this mission revision");
    if (!this.sequenceRepository.claim(adapter.adapterId, envelope.event.aircraftId, envelope.sequence)) {
      throw new TelemetryServiceError(409, "TELEMETRY_SEQUENCE_OUT_OF_ORDER", "telemetry sequence must increase monotonically");
    }
    const result = Object.freeze({ adapterId: adapter.adapterId, revisionId: envelope.revisionId, sequence: envelope.sequence, status: "accepted" as const, event: envelope.event });
    const stream = this.streams.get(envelope.revisionId) ?? [];
    stream.push(result);
    if (stream.length > MAX_RETAINED_EVENTS) stream.splice(0, stream.length - MAX_RETAINED_EVENTS);
    this.streams.set(envelope.revisionId, stream);
    const subscribers = this.subscribers.get(envelope.revisionId);
    for (const subscriber of subscribers ?? []) {
      if (!subscriber.push(result)) {
        subscribers!.delete(subscriber);
        subscriber.close();
      }
    }
    if (subscribers?.size === 0) this.subscribers.delete(envelope.revisionId);
    return result;
  }

  public snapshot(revisionId: string, window: number): readonly TelemetryIngestionResult[] {
    if (!Number.isInteger(window) || window < 1 || window > 100) throw new TelemetryServiceError(400, "TELEMETRY_WINDOW_INVALID", "telemetry replay window must be between 1 and 100");
    return Object.freeze([...(this.streams.get(revisionId) ?? []).slice(-window)]);
  }

  public subscribe(revisionId: string, listener: Subscriber["push"], close: Subscriber["close"] = () => undefined): () => void {
    const listeners = this.subscribers.get(revisionId) ?? new Set<Subscriber>();
    const subscriber = Object.freeze({ push: listener, close });
    listeners.add(subscriber);
    this.subscribers.set(revisionId, listeners);
    let active = true;
    return () => {
      if (!active) return;
      active = false;
      listeners.delete(subscriber);
      if (listeners.size === 0) this.subscribers.delete(revisionId);
    };
  }

  public activeSubscriberCount(): number {
    let total = 0;
    for (const listeners of this.subscribers.values()) total += listeners.size;
    return total;
  }

  public close(): void {
    for (const subscribers of this.subscribers.values()) for (const subscriber of subscribers) subscriber.close();
    this.subscribers.clear();
  }
}

function parseEnvelope(input: unknown): TelemetryEnvelope {
  if (input === null || typeof input !== "object" || Array.isArray(input)) throw new TelemetryServiceError(400, "INVALID_TELEMETRY_ENVELOPE", "telemetry payload must be an object");
  const body = input as Record<string, unknown>;
  for (const key of Object.keys(body)) if (!["revisionId", "sequence", "event"].includes(key)) throw new TelemetryServiceError(400, "INVALID_TELEMETRY_ENVELOPE", "telemetry payload contains an unsupported field");
  const revisionId = boundedText(body.revisionId, "revisionId");
  if (typeof body.sequence !== "number" || !Number.isSafeInteger(body.sequence) || body.sequence < 0) throw new TelemetryServiceError(400, "INVALID_TELEMETRY_SEQUENCE", "telemetry sequence must be a non-negative safe integer");
  let event: CanonicalTelemetry;
  try {
    if (Buffer.byteLength(canonicalJson(body.event), "utf8") > MAX_EVENT_BYTES) throw new TelemetryServiceError(413, "TELEMETRY_EVENT_TOO_LARGE", "telemetry event exceeds the configured limit");
    event = canonicalizeTelemetry(body.event);
  } catch (error) {
    if (error instanceof TelemetryServiceError) throw error;
    throw new TelemetryServiceError(400, "INVALID_TELEMETRY", error instanceof TelemetryValidationError ? error.message : "telemetry event is invalid");
  }
  for (const value of [event.eventId, event.aircraftId, ...event.sourcePackageIds]) {
    if (value.length > MAX_TEXT_LENGTH) throw new TelemetryServiceError(400, "INVALID_TELEMETRY", "telemetry identifiers exceed the configured bound");
  }
  return Object.freeze({ revisionId, sequence: body.sequence, event });
}

function boundedText(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "" || value !== value.trim() || value.includes("\0") || value.length > MAX_TEXT_LENGTH) throw new TelemetryServiceError(400, "INVALID_TELEMETRY_ENVELOPE", `${field} is invalid`);
  return value;
}
