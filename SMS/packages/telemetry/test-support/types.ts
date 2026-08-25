import type { CanonicalTelemetry } from "../src/types.js";

export type TelemetryRecordStatus = "accepted" | "degraded" | "rejected";
export interface TelemetryReplayRecord { readonly eventId: string; readonly aircraftId: string; readonly status: TelemetryRecordStatus; readonly rawHash: string; readonly reason?: string; readonly degradedReason?: string; readonly event?: CanonicalTelemetry }
export interface TelemetryRetentionRecord { readonly eventId: string; readonly aircraftId: string; readonly observedAtUtc: string; readonly retainedUntilUtc: string; readonly rawHash: string; readonly sourcePackageIds: readonly string[] }
export interface ReplayGatewayOptions { readonly adapterId?: string; readonly aircraftId: string; readonly now?: () => string; readonly maxDelayMs?: number; readonly retentionDays?: number }
export interface ReplayFixtureResult { readonly records: readonly TelemetryReplayRecord[]; readonly retentionRecords: readonly TelemetryRetentionRecord[]; readonly signature: string }
