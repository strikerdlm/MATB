import { createHash } from "node:crypto";
import { canonicalJson } from "@fac-isr/evidence";
import type {
  CanonicalTelemetry,
  ReadOnlyTelemetryAdapter,
  ReplayGatewayOptions,
  TelemetryReplayRecord,
  TelemetryRetentionRecord,
  TelemetryValidationOptions,
} from "./types.js";

const UTC_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/;
const TOP_LEVEL_FIELDS = new Set(["eventId", "aircraftId", "observedAtUtc", "position", "motion", "energy", "platform", "route", "sourcePackageIds"]);
const NESTED_FIELDS: Readonly<Record<string, ReadonlySet<string>>> = {
  position: new Set(["lat", "lon", "altitudeMslM", "heightAglM"]),
  motion: new Set(["headingDeg", "groundSpeedKt", "verticalRateFpm"]),
  energy: new Set(["stateOfChargePercent", "voltageV", "currentA", "temperatureC", "reserveAtRecoveryPercent"]),
  platform: new Set(["propulsion", "gnss", "c2Link"]),
  route: new Set(["legId", "crossTrackM", "approvedArea"]),
};

export class TelemetryValidationError extends Error {
  public readonly code = "INVALID_TELEMETRY";

  public constructor(message: string) {
    super(message);
    this.name = "TelemetryValidationError";
  }
}

function objectInput(value: unknown, field: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new TelemetryValidationError(`${field} must be an object`);
  return value as Record<string, unknown>;
}

function text(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "" || value !== value.trim() || value.includes("\0")) throw new TelemetryValidationError(`${field} must be non-empty text`);
  return value;
}

function finiteNumber(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new TelemetryValidationError(`${field} must be finite`);
  return value;
}

function optionalNumber(value: unknown, field: string): number | undefined {
  return value === undefined ? undefined : finiteNumber(value, field);
}

function validateKeys(value: Record<string, unknown>, allowed: ReadonlySet<string>, field: string): void {
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) throw new TelemetryValidationError(`unsupported telemetry field ${field}.${key}`);
  }
}

function utc(value: unknown): string {
  const candidate = text(value, "observedAtUtc");
  if (!UTC_PATTERN.test(candidate)) throw new TelemetryValidationError("observedAtUtc must be UTC ISO-8601");
  const timestamp = new Date(candidate);
  if (!Number.isFinite(timestamp.getTime())) throw new TelemetryValidationError("observedAtUtc must be a valid instant");
  return timestamp.toISOString();
}

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    for (const child of Object.values(value as Record<string, unknown>)) deepFreeze(child);
    Object.freeze(value);
  }
  return value;
}

export function canonicalizeTelemetry(input: unknown, options: TelemetryValidationOptions = {}): CanonicalTelemetry {
  const raw = objectInput(input, "telemetry");
  validateKeys(raw, TOP_LEVEL_FIELDS, "telemetry");
  const eventId = text(raw.eventId, "eventId");
  const aircraftId = text(raw.aircraftId, "aircraftId");
  if (options.aircraftId !== undefined && aircraftId !== options.aircraftId) throw new TelemetryValidationError("aircraftId is not assigned to this gateway");
  const observedAtUtc = utc(raw.observedAtUtc);
  const sourcePackageIds = raw.sourcePackageIds;
  if (!Array.isArray(sourcePackageIds) || sourcePackageIds.length === 0) throw new TelemetryValidationError("sourcePackageIds must contain at least one package");
  const packageIds = sourcePackageIds.map((id) => text(id, "sourcePackageIds"));

  let position: CanonicalTelemetry["position"];
  if (raw.position !== undefined) {
    const value = objectInput(raw.position, "position");
    validateKeys(value, NESTED_FIELDS.position, "position");
    const lat = finiteNumber(value.lat, "position.lat");
    const lon = finiteNumber(value.lon, "position.lon");
    if (lat < -90 || lat > 90) throw new TelemetryValidationError("position.lat must be between -90 and 90");
    if (lon < -180 || lon > 180) throw new TelemetryValidationError("position.lon must be between -180 and 180");
    const altitudeMslM = optionalNumber(value.altitudeMslM, "position.altitudeMslM");
    const heightAglM = optionalNumber(value.heightAglM, "position.heightAglM");
    if (heightAglM !== undefined && heightAglM < 0) throw new TelemetryValidationError("position.heightAglM must be non-negative");
    position = { lat, lon, ...(altitudeMslM === undefined ? {} : { altitudeMslM }), ...(heightAglM === undefined ? {} : { heightAglM }) };
  }

  let motion: CanonicalTelemetry["motion"];
  if (raw.motion !== undefined) {
    const value = objectInput(raw.motion, "motion");
    validateKeys(value, NESTED_FIELDS.motion, "motion");
    const headingDeg = optionalNumber(value.headingDeg, "motion.headingDeg");
    const groundSpeedKt = optionalNumber(value.groundSpeedKt, "motion.groundSpeedKt");
    const verticalRateFpm = optionalNumber(value.verticalRateFpm, "motion.verticalRateFpm");
    if (headingDeg !== undefined && (headingDeg < 0 || headingDeg >= 360)) throw new TelemetryValidationError("motion.headingDeg must be in [0, 360)");
    if (groundSpeedKt !== undefined && groundSpeedKt < 0) throw new TelemetryValidationError("motion.groundSpeedKt must be non-negative");
    motion = { ...(headingDeg === undefined ? {} : { headingDeg }), ...(groundSpeedKt === undefined ? {} : { groundSpeedKt }), ...(verticalRateFpm === undefined ? {} : { verticalRateFpm }) };
  }

  let energy: CanonicalTelemetry["energy"];
  if (raw.energy !== undefined) {
    const value = objectInput(raw.energy, "energy");
    validateKeys(value, NESTED_FIELDS.energy, "energy");
    const stateOfChargePercent = optionalNumber(value.stateOfChargePercent, "energy.stateOfChargePercent");
    const voltageV = optionalNumber(value.voltageV, "energy.voltageV");
    const currentA = optionalNumber(value.currentA, "energy.currentA");
    const temperatureC = optionalNumber(value.temperatureC, "energy.temperatureC");
    const reserveAtRecoveryPercent = optionalNumber(value.reserveAtRecoveryPercent, "energy.reserveAtRecoveryPercent");
    if (stateOfChargePercent !== undefined && (stateOfChargePercent < 0 || stateOfChargePercent > 100)) throw new TelemetryValidationError("energy.stateOfChargePercent must be in [0, 100]");
    if (reserveAtRecoveryPercent !== undefined && (reserveAtRecoveryPercent < 0 || reserveAtRecoveryPercent > 100)) throw new TelemetryValidationError("energy.reserveAtRecoveryPercent must be in [0, 100]");
    energy = { ...(stateOfChargePercent === undefined ? {} : { stateOfChargePercent }), ...(voltageV === undefined ? {} : { voltageV }), ...(currentA === undefined ? {} : { currentA }), ...(temperatureC === undefined ? {} : { temperatureC }), ...(reserveAtRecoveryPercent === undefined ? {} : { reserveAtRecoveryPercent }) };
  }

  let platform: CanonicalTelemetry["platform"];
  if (raw.platform !== undefined) {
    const value = objectInput(raw.platform, "platform");
    validateKeys(value, NESTED_FIELDS.platform, "platform");
    const propulsion = value.propulsion === undefined ? undefined : text(value.propulsion, "platform.propulsion");
    const gnss = value.gnss === undefined ? undefined : text(value.gnss, "platform.gnss");
    const c2Link = value.c2Link === undefined ? undefined : text(value.c2Link, "platform.c2Link");
    if (propulsion !== undefined && !["normal", "degraded", "unknown"].includes(propulsion)) throw new TelemetryValidationError("platform.propulsion is unsupported");
    if (gnss !== undefined && !["normal", "degraded", "unknown"].includes(gnss)) throw new TelemetryValidationError("platform.gnss is unsupported");
    if (c2Link !== undefined && !["normal", "degraded", "lost"].includes(c2Link)) throw new TelemetryValidationError("platform.c2Link is unsupported");
    platform = { ...(propulsion === undefined ? {} : { propulsion: propulsion as "normal" | "degraded" | "unknown" }), ...(gnss === undefined ? {} : { gnss: gnss as "normal" | "degraded" | "unknown" }), ...(c2Link === undefined ? {} : { c2Link: c2Link as "normal" | "degraded" | "lost" }) };
  }

  let route: CanonicalTelemetry["route"];
  if (raw.route !== undefined) {
    const value = objectInput(raw.route, "route");
    validateKeys(value, NESTED_FIELDS.route, "route");
    const legId = value.legId === undefined ? undefined : text(value.legId, "route.legId");
    const crossTrackM = optionalNumber(value.crossTrackM, "route.crossTrackM");
    if (crossTrackM !== undefined && crossTrackM < 0) throw new TelemetryValidationError("route.crossTrackM must be non-negative");
    if (value.approvedArea !== undefined && typeof value.approvedArea !== "boolean") throw new TelemetryValidationError("route.approvedArea must be boolean");
    route = { ...(legId === undefined ? {} : { legId }), ...(crossTrackM === undefined ? {} : { crossTrackM }), ...(value.approvedArea === undefined ? {} : { approvedArea: value.approvedArea }) };
  }

  return deepFreeze({ eventId, aircraftId, observedAtUtc, ...(position === undefined ? {} : { position }), ...(motion === undefined ? {} : { motion }), ...(energy === undefined ? {} : { energy }), ...(platform === undefined ? {} : { platform }), ...(route === undefined ? {} : { route }), sourcePackageIds: packageIds });
}

export function rawTelemetryHash(input: unknown): string {
  try {
    return createHash("sha256").update(canonicalJson(input)).digest("hex");
  } catch {
    return createHash("sha256").update(String(input)).digest("hex");
  }
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
    this.adapterId = options.adapterId ?? "replay-fixture";
    this.aircraftId = text(options.aircraftId, "aircraftId");
    this.now = options.now ?? (() => new Date().toISOString());
    this.maxDelayMs = options.maxDelayMs ?? 30_000;
    this.retentionDays = options.retentionDays ?? 365;
  }

  public async replay(inputs: readonly unknown[]): Promise<readonly TelemetryReplayRecord[]> {
    if (!Array.isArray(inputs)) throw new TelemetryValidationError("replay events must be an array");
    for (const input of inputs) this.ingest(input);
    return this.records.map((record) => Object.freeze({ ...record }));
  }

  public acceptedEvents(): readonly CanonicalTelemetry[] {
    return this.records.filter((record) => record.event !== undefined && record.status !== "rejected").map((record) => record.event!);
  }

  public recordsSnapshot(): readonly TelemetryReplayRecord[] {
    return this.records.map((record) => Object.freeze({ ...record }));
  }

  public retentionRecords(): readonly TelemetryRetentionRecord[] {
    return this.retention.map((record) => Object.freeze({ ...record, sourcePackageIds: Object.freeze([...record.sourcePackageIds]) }));
  }

  /** Records a transport dropout without inventing a position or control action. */
  public recordDropout(observedAtUtc = this.now()): TelemetryReplayRecord {
    const eventId = `dropout:${this.records.length}`;
    const record = Object.freeze({
      eventId,
      aircraftId: this.aircraftId,
      status: "degraded" as const,
      reason: "DROPOUT",
      rawHash: rawTelemetryHash({ eventId, aircraftId: this.aircraftId, observedAtUtc }),
    });
    this.records.push(record);
    return record;
  }

  public markDropout(observedAtUtc = this.now()): TelemetryReplayRecord {
    return this.recordDropout(observedAtUtc);
  }

  private ingest(input: unknown): void {
    const raw = input !== null && typeof input === "object" && !Array.isArray(input) ? input as Record<string, unknown> : {};
    const eventId = typeof raw.eventId === "string" ? raw.eventId : "unknown";
    const aircraftId = typeof raw.aircraftId === "string" ? raw.aircraftId : this.aircraftId;
    const rawHash = rawTelemetryHash(input);
    try {
      const event = canonicalizeTelemetry(input, { aircraftId: this.aircraftId });
      if (this.acceptedIds.has(event.eventId)) {
        this.records.push(Object.freeze({ eventId: event.eventId, aircraftId: event.aircraftId, status: "rejected", reason: "DUPLICATE_EVENT", rawHash }));
        return;
      }
      const observedEpochMs = Date.parse(event.observedAtUtc);
      const delayMs = Date.parse(this.now()) - observedEpochMs;
      if (this.lastObservedEpochMs !== undefined && observedEpochMs < this.lastObservedEpochMs && delayMs <= this.maxDelayMs) {
        this.records.push(Object.freeze({ eventId: event.eventId, aircraftId: event.aircraftId, status: "rejected", reason: "OUT_OF_ORDER", rawHash }));
        return;
      }
      const degraded = delayMs > this.maxDelayMs;
      const status = degraded ? "degraded" as const : "accepted" as const;
      this.records.push(Object.freeze({ eventId: event.eventId, aircraftId: event.aircraftId, status, ...(degraded ? { degradedReason: "DELAYED" } : {}), rawHash, event }));
      this.acceptedIds.add(event.eventId);
      if (this.lastObservedEpochMs === undefined || observedEpochMs > this.lastObservedEpochMs) this.lastObservedEpochMs = observedEpochMs;
      const retainedUntilUtc = new Date(observedEpochMs + this.retentionDays * 24 * 60 * 60 * 1000).toISOString();
      this.retention.push(Object.freeze({ eventId: event.eventId, aircraftId: event.aircraftId, observedAtUtc: event.observedAtUtc, retainedUntilUtc, rawHash, sourcePackageIds: Object.freeze([...event.sourcePackageIds]) }));
    } catch (error) {
      this.records.push(Object.freeze({ eventId, aircraftId, status: "rejected", reason: error instanceof TelemetryValidationError ? error.message : "INVALID_TELEMETRY", rawHash }));
    }
  }
}

export class ReplayTelemetryAdapter implements ReadOnlyTelemetryAdapter {
  public readonly adapterId: string;
  public readonly aircraftId: string;
  private readonly inputs: readonly unknown[];
  private readonly gateway: ReplayGateway;
  private cursor = 0;
  private connected = false;
  private closed = false;

  public constructor(inputs: readonly unknown[], options: ReplayGatewayOptions) {
    this.inputs = inputs;
    this.gateway = new ReplayGateway(options);
    this.adapterId = this.gateway.adapterId;
    this.aircraftId = this.gateway.aircraftId;
  }

  public async connect(signal: AbortSignal): Promise<void> {
    if (signal.aborted) throw new Error("telemetry adapter connection aborted");
    if (this.closed) throw new Error("telemetry adapter is closed");
    if (!this.connected) {
      await this.gateway.replay(this.inputs);
      this.connected = true;
    }
  }

  public async readStatus(signal: AbortSignal): Promise<CanonicalTelemetry | null> {
    await this.connect(signal);
    if (signal.aborted || this.closed) return null;
    const events = this.gateway.acceptedEvents();
    return events[this.cursor++] ?? null;
  }

  public async subscribe(listener: (event: CanonicalTelemetry) => void, signal: AbortSignal): Promise<void> {
    await this.connect(signal);
    while (!signal.aborted && !this.closed) {
      const event = await this.readStatus(signal);
      if (event === null) return;
      listener(event);
    }
  }

  public async close(): Promise<void> {
    this.closed = true;
  }
}

/** A fixture adapter used to prove the vendor boundary remains read-only. */
export class ReadOnlyTelemetryAdapterFixture implements ReadOnlyTelemetryAdapter {
  private readonly delegate: ReplayTelemetryAdapter;
  public readonly adapterId: string;
  public readonly aircraftId: string;

  public constructor(inputs: readonly unknown[] = [], options: ReplayGatewayOptions = { aircraftId: "fixture-aircraft" }) {
    this.delegate = new ReplayTelemetryAdapter(inputs, options);
    this.adapterId = this.delegate.adapterId;
    this.aircraftId = this.delegate.aircraftId;
  }

  public connect(signal: AbortSignal): Promise<void> {
    return this.delegate.connect(signal);
  }

  public readStatus(signal: AbortSignal): Promise<CanonicalTelemetry | null> {
    return this.delegate.readStatus(signal);
  }

  public subscribe(listener: (event: CanonicalTelemetry) => void, signal: AbortSignal): Promise<void> {
    return this.delegate.subscribe(listener, signal);
  }

  public close(): Promise<void> {
    return this.delegate.close();
  }
}
