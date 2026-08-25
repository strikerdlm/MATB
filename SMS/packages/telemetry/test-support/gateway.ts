import { createHash } from "node:crypto";
import { canonicalJson } from "@fac-isr/evidence";
import { canonicalizeTelemetry, TelemetryValidationError } from "../src/gateway.js";
import type { CanonicalTelemetry, ReadOnlyTelemetryAdapter } from "../src/types.js";
import type { ReplayGatewayOptions, TelemetryReplayRecord, TelemetryRetentionRecord } from "./types.js";

function rawTelemetryHash(input: unknown): string {
  try { return createHash("sha256").update(canonicalJson(input)).digest("hex"); }
  catch { return createHash("sha256").update(String(input)).digest("hex"); }
}

export class ReplayGateway {
  public readonly adapterId: string;
  public readonly aircraftId: string;
  private readonly now: () => string;
  private readonly maxDelayMs: number;
  private readonly retentionDays: number;
  private readonly records: TelemetryReplayRecord[] = [];
  private readonly retention: TelemetryRetentionRecord[] = [];
  private readonly acceptedIds = new Set<string>();
  private lastObservedEpochMs?: number;
  public constructor(options: ReplayGatewayOptions) {
    if (!Number.isInteger(options.maxDelayMs ?? 30_000) || (options.maxDelayMs ?? 30_000) <= 0) throw new RangeError("maxDelayMs must be positive");
    if (!Number.isInteger(options.retentionDays ?? 365) || (options.retentionDays ?? 365) < 365) throw new RangeError("retentionDays cannot be shorter than one year");
    if (typeof options.aircraftId !== "string" || options.aircraftId.trim() === "" || options.aircraftId !== options.aircraftId.trim()) throw new TelemetryValidationError("aircraftId must be non-empty text");
    this.adapterId = options.adapterId ?? "replay-fixture";
    this.aircraftId = options.aircraftId;
    this.now = options.now ?? (() => new Date().toISOString());
    this.maxDelayMs = options.maxDelayMs ?? 30_000;
    this.retentionDays = options.retentionDays ?? 365;
  }
  public async replay(inputs: readonly unknown[]): Promise<readonly TelemetryReplayRecord[]> { if (!Array.isArray(inputs)) throw new TelemetryValidationError("replay events must be an array"); for (const input of inputs) this.ingest(input); return this.records.map((record) => Object.freeze({ ...record })); }
  public acceptedEvents(): readonly CanonicalTelemetry[] { return this.records.filter((record) => record.event !== undefined && record.status !== "rejected").map((record) => record.event!); }
  public recordsSnapshot(): readonly TelemetryReplayRecord[] { return this.records.map((record) => Object.freeze({ ...record })); }
  public retentionRecords(): readonly TelemetryRetentionRecord[] { return this.retention.map((record) => Object.freeze({ ...record, sourcePackageIds: Object.freeze([...record.sourcePackageIds]) })); }
  public recordDropout(observedAtUtc = this.now()): TelemetryReplayRecord { const eventId = `dropout:${this.records.length}`; const record = Object.freeze({ eventId, aircraftId: this.aircraftId, status: "degraded" as const, reason: "DROPOUT", rawHash: rawTelemetryHash({ eventId, aircraftId: this.aircraftId, observedAtUtc }) }); this.records.push(record); return record; }
  public markDropout(observedAtUtc = this.now()): TelemetryReplayRecord { return this.recordDropout(observedAtUtc); }
  private ingest(input: unknown): void {
    const raw = input !== null && typeof input === "object" && !Array.isArray(input) ? input as Record<string, unknown> : {};
    const eventId = typeof raw.eventId === "string" ? raw.eventId : "unknown";
    const aircraftId = typeof raw.aircraftId === "string" ? raw.aircraftId : this.aircraftId;
    const rawHash = rawTelemetryHash(input);
    try {
      const event = canonicalizeTelemetry(input, { aircraftId: this.aircraftId });
      if (this.acceptedIds.has(event.eventId)) { this.records.push(Object.freeze({ eventId: event.eventId, aircraftId: event.aircraftId, status: "rejected", reason: "DUPLICATE_EVENT", rawHash })); return; }
      const observedEpochMs = Date.parse(event.observedAtUtc); const delayMs = Date.parse(this.now()) - observedEpochMs;
      if (this.lastObservedEpochMs !== undefined && observedEpochMs < this.lastObservedEpochMs && delayMs <= this.maxDelayMs) { this.records.push(Object.freeze({ eventId: event.eventId, aircraftId: event.aircraftId, status: "rejected", reason: "OUT_OF_ORDER", rawHash })); return; }
      const degraded = delayMs > this.maxDelayMs; const status = degraded ? "degraded" as const : "accepted" as const;
      this.records.push(Object.freeze({ eventId: event.eventId, aircraftId: event.aircraftId, status, ...(degraded ? { degradedReason: "DELAYED" } : {}), rawHash, event })); this.acceptedIds.add(event.eventId);
      if (this.lastObservedEpochMs === undefined || observedEpochMs > this.lastObservedEpochMs) this.lastObservedEpochMs = observedEpochMs;
      this.retention.push(Object.freeze({ eventId: event.eventId, aircraftId: event.aircraftId, observedAtUtc: event.observedAtUtc, retainedUntilUtc: new Date(observedEpochMs + this.retentionDays * 86_400_000).toISOString(), rawHash, sourcePackageIds: Object.freeze([...event.sourcePackageIds]) }));
    } catch (error) { this.records.push(Object.freeze({ eventId, aircraftId, status: "rejected", reason: error instanceof TelemetryValidationError ? error.message : "INVALID_TELEMETRY", rawHash })); }
  }
}

export class ReplayTelemetryAdapter implements ReadOnlyTelemetryAdapter {
  public readonly adapterId: string; public readonly aircraftId: string; private readonly gateway: ReplayGateway; private cursor = 0; private connected = false; private closed = false;
  public constructor(private readonly inputs: readonly unknown[], options: ReplayGatewayOptions) { this.gateway = new ReplayGateway(options); this.adapterId = this.gateway.adapterId; this.aircraftId = this.gateway.aircraftId; }
  public async connect(signal: AbortSignal): Promise<void> { if (signal.aborted) throw new Error("telemetry adapter connection aborted"); if (this.closed) throw new Error("telemetry adapter is closed"); if (!this.connected) { await this.gateway.replay(this.inputs); this.connected = true; } }
  public async readStatus(signal: AbortSignal): Promise<CanonicalTelemetry | null> { await this.connect(signal); if (signal.aborted || this.closed) return null; return this.gateway.acceptedEvents()[this.cursor++] ?? null; }
  public async subscribe(listener: (event: CanonicalTelemetry) => void, signal: AbortSignal): Promise<void> { await this.connect(signal); while (!signal.aborted && !this.closed) { const event = await this.readStatus(signal); if (event === null) return; listener(event); } }
  public async close(): Promise<void> { this.closed = true; }
}

export class ReadOnlyTelemetryAdapterFixture implements ReadOnlyTelemetryAdapter {
  private readonly delegate: ReplayTelemetryAdapter; public readonly adapterId: string; public readonly aircraftId: string;
  public constructor(inputs: readonly unknown[] = [], options: ReplayGatewayOptions = { aircraftId: "fixture-aircraft" }) { this.delegate = new ReplayTelemetryAdapter(inputs, options); this.adapterId = this.delegate.adapterId; this.aircraftId = this.delegate.aircraftId; }
  public connect(signal: AbortSignal): Promise<void> { return this.delegate.connect(signal); }
  public readStatus(signal: AbortSignal): Promise<CanonicalTelemetry | null> { return this.delegate.readStatus(signal); }
  public subscribe(listener: (event: CanonicalTelemetry) => void, signal: AbortSignal): Promise<void> { return this.delegate.subscribe(listener, signal); }
  public close(): Promise<void> { return this.delegate.close(); }
}
