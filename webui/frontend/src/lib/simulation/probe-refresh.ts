import type { ActiveProbePayload, SessionView } from "@/types/simulation";

export function sameProbe(
  a: ActiveProbePayload | null,
  b: ActiveProbePayload | null,
): boolean {
  if (!a || !b) return a === b;
  return (
    a.kind === b.kind &&
    ("probe_id" in a ? a.probe_id : null) ===
      ("probe_id" in b ? b.probe_id : null)
  );
}

/** A slow response to one answer must not clear the next streamed question. */
export function reconcileProbeRefresh(
  currentProbe: ActiveProbePayload | null,
  answeredProbe: ActiveProbePayload | null,
  refreshed: SessionView,
) {
  const newerProbe =
    currentProbe !== null && !sameProbe(currentProbe, answeredProbe);
  const activeProbe = newerProbe
    ? currentProbe
    : (refreshed.active_probe ?? null);
  const session = newerProbe
    ? {
        ...refreshed,
        lifecycle: "PAUSED" as const,
        protocol_phase: `${currentProbe.kind}_ACTIVE`,
        active_probe: currentProbe,
      }
    : refreshed;
  return {
    session,
    activeProbe,
    concealOperationalState: activeProbe?.kind === "SAGAT",
  };
}
