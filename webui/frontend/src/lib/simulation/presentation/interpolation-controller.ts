import { interpolateSnapshot } from "../interpolation";
import type { WorldSnapshot } from "@/types/simulation";

export const INTERPOLATION_MS = 320;
export type InterpolationPolicy = "linear-320-v1" | "none-v1";

/** A bounded owner: no animation remains scheduled after finish or cancellation. */
export function animateSnapshot(before: WorldSnapshot | null | undefined, after: WorldSnapshot, enabled: boolean,
  draw: (snapshot: WorldSnapshot) => void) {
  if (!enabled || !before || before.block_id !== after.block_id || before.simulation_time_ms >= after.simulation_time_ms) {
    draw(after); return () => {};
  }
  const started = performance.now();
  let frame = 0, cancelled = false;
  const sample = (fraction: number) => interpolateSnapshot(before, after,
    before.simulation_time_ms + (after.simulation_time_ms-before.simulation_time_ms)*fraction);
  draw(sample(0));
  function update(now: number) {
    if (cancelled) return;
    const fraction = Math.max(0, Math.min(1, (now-started)/INTERPOLATION_MS));
    draw(fraction === 1 ? after : sample(fraction));
    if (fraction < 1) frame = requestAnimationFrame(update);
  }
  frame = requestAnimationFrame(update);
  return () => { cancelled = true; cancelAnimationFrame(frame); };
}
