export interface CanonicalTelemetry {
  readonly eventId: string;
  readonly aircraftId: string;
  readonly observedAtUtc: string;
  readonly position?: Readonly<{ lat: number; lon: number; altitudeMslM?: number; heightAglM?: number }>;
  readonly motion?: Readonly<{ headingDeg?: number; groundSpeedKt?: number; verticalRateFpm?: number }>;
  readonly energy?: Readonly<{ stateOfChargePercent?: number; voltageV?: number; currentA?: number; temperatureC?: number; reserveAtRecoveryPercent?: number }>;
  readonly platform?: Readonly<{ propulsion?: "normal" | "degraded" | "unknown"; gnss?: "normal" | "degraded" | "unknown"; c2Link?: "normal" | "degraded" | "lost" }>;
  readonly route?: Readonly<{ legId?: string; crossTrackM?: number; approvedArea?: boolean }>;
  readonly sourcePackageIds: readonly string[];
}

export interface ReadOnlyTelemetryAdapter {
  readonly adapterId: string;
  readonly aircraftId: string;
  connect(signal: AbortSignal): Promise<void>;
  readStatus(signal: AbortSignal): Promise<CanonicalTelemetry | null>;
  subscribe(listener: (event: CanonicalTelemetry) => void, signal: AbortSignal): Promise<void>;
  close(): Promise<void>;
}

export interface TelemetryValidationOptions {
  readonly aircraftId?: string;
}
