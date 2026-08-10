import {
  ReplayGateway,
  signReplayFixture,
  type ReplayFixtureResult,
  type TelemetryReplayRecord,
  type TelemetryRetentionRecord,
} from "@fac-isr/telemetry";

export class TelemetryServiceError extends Error {
  public constructor(
    public readonly statusCode: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "TelemetryServiceError";
  }
}

interface StoredReplay {
  readonly records: readonly TelemetryReplayRecord[];
  readonly retentionRecords: readonly TelemetryRetentionRecord[];
}

export class TelemetryService {
  private readonly streams = new Map<string, StoredReplay>();

  public async replay(input: unknown): Promise<ReplayFixtureResult> {
    const body = objectInput(input);
    if (!Array.isArray(body.events)) throw new TelemetryServiceError(400, "REPLAY_EVENTS_REQUIRED", "replay events must be an array");
    const aircraftId = required(body.aircraftId, "aircraftId");
    const signature = required(body.signature, "signature");
    if (!/^[a-f0-9]{64}$/.test(signature) || signature !== signReplayFixture(body.events)) {
      throw new TelemetryServiceError(400, "REPLAY_SIGNATURE_INVALID", "replay fixture signature is invalid");
    }
    const gateway = new ReplayGateway({
      aircraftId,
      adapterId: typeof body.adapterId === "string" ? body.adapterId : undefined,
      maxDelayMs: typeof body.maxDelayMs === "number" ? body.maxDelayMs : undefined,
      retentionDays: typeof body.retentionDays === "number" ? body.retentionDays : undefined,
    });
    const records = await gateway.replay(body.events);
    const retentionRecords = gateway.retentionRecords();
    const revisionId = typeof body.revisionId === "string" && body.revisionId.trim() !== "" ? body.revisionId : "__unbound__";
    this.streams.set(revisionId, { records: records.filter((record) => record.event !== undefined && record.status !== "rejected"), retentionRecords });
    return Object.freeze({ records, retentionRecords, signature });
  }

  public stream(revisionId: string): readonly TelemetryReplayRecord[] {
    return this.streams.get(revisionId)?.records ?? [];
  }
}

function objectInput(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new TelemetryServiceError(400, "INVALID_REPLAY", "replay payload must be an object");
  return value as Record<string, unknown>;
}

function required(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "" || value !== value.trim() || value.includes("\0")) throw new TelemetryServiceError(400, "INVALID_REPLAY", `${field} is required`);
  return value;
}
