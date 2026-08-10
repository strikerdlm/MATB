import { useMemo, useState } from "react";

export interface TelemetryEvent {
  readonly eventId: string;
  readonly revisionId: string;
  readonly capturedAtUtc: string;
  readonly status: "nominal" | "degraded" | "rejected";
  readonly detail: string;
}

export type TelemetryConnectionStatus = "idle" | "nominal" | "degraded";

export interface TelemetryState {
  readonly events: readonly TelemetryEvent[];
  readonly status: TelemetryConnectionStatus;
  readonly acknowledgedEventIds: readonly string[];
  readonly acknowledge: (eventId: string) => void;
}

/** Local replay state only: no network transport or command-capable adapter. */
export function useTelemetry(revisionId: string, initialEvents: readonly TelemetryEvent[] = []): TelemetryState {
  const [acknowledgedEventIds, setAcknowledgedEventIds] = useState<readonly string[]>([]);
  const events = useMemo(() => initialEvents.filter((event) => event.revisionId === revisionId), [initialEvents, revisionId]);
  const status: TelemetryConnectionStatus = events.length === 0 ? "idle" : events.some((event) => event.status === "degraded") ? "degraded" : "nominal";
  const acknowledge = (eventId: string): void => setAcknowledgedEventIds((current) => current.includes(eventId) ? current : [...current, eventId]);
  return { events, status, acknowledgedEventIds, acknowledge };
}
