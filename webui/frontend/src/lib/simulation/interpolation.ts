import type { AircraftSnapshot, PointMM, WorldSnapshot } from "@/types/simulation";

function cloneSnapshot(snapshot: WorldSnapshot): WorldSnapshot {
  return JSON.parse(JSON.stringify(snapshot)) as WorldSnapshot;
}
function lerp(start: number, end: number, fraction: number): number {
  return start + (end - start) * fraction;
}

/**
 * Build a display-only frame between authoritative snapshots.
 *
 * The newer snapshot supplies every field except matching aircraft x/y.  No
 * caller-owned object is ever mutated, so an animation frame cannot alter
 * simulation truth or the replayable state in the store.
 */
export function interpolateSnapshot(
  before: WorldSnapshot,
  after: WorldSnapshot,
  simulationTimeMs: number,
): WorldSnapshot {
  const rendered = cloneSnapshot(after);
  const duration = after.simulation_time_ms - before.simulation_time_ms;
  if (duration <= 0 || !Number.isFinite(simulationTimeMs)) return rendered;
  const fraction = Math.min(
    1,
    Math.max(0, (simulationTimeMs - before.simulation_time_ms) / duration),
  );
  for (const [aircraftId, aircraft] of Object.entries(rendered.aircraft)) {
    const previous: AircraftSnapshot | undefined = before.aircraft[aircraftId];
    if (!previous) continue;
    const position: PointMM = {
      x_mm: lerp(previous.position.x_mm, aircraft.position.x_mm, fraction),
      y_mm: lerp(previous.position.y_mm, aircraft.position.y_mm, fraction),
    };
    rendered.aircraft[aircraftId] = { ...aircraft, position };
  }
  return rendered;
}
