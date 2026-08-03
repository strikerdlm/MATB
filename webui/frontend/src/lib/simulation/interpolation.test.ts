import { describe, expect, it } from "vitest";
import { interpolateSnapshot } from "@/lib/simulation/interpolation";
import type { WorldSnapshot } from "@/types/simulation";

function snapshotAt(simulationTimeMs: number, x_mm: number, y_mm: number): WorldSnapshot {
  return {
    simulation_time_ms: simulationTimeMs,
    state_version: simulationTimeMs / 250,
    aircraft: {
      "UAS-01": {
        aircraft_id: "UAS-01",
        label: "UAS-01",
        position: { x_mm, y_mm },
        heading_mdeg: 0,
        energy_units: 100,
        predicted_home_reserve_units: 20,
        mode: "SEARCH",
        link: "NOMINAL",
        sensor: "NOMINAL",
        assigned_sector_id: "S1",
        route: [],
        mission_progress_ppm: 100,
      },
    },
  } as unknown as WorldSnapshot;
}

describe("interpolateSnapshot", () => {
  it("interpolates display positions without mutating either snapshot", () => {
    const before = snapshotAt(0, 0, 0);
    const after = snapshotAt(250, 1_000, 500);
    Object.freeze(before.aircraft["UAS-01"].position);
    Object.freeze(after.aircraft["UAS-01"].position);

    const rendered = interpolateSnapshot(before, after, 125);

    expect(rendered.aircraft["UAS-01"].position).toEqual({ x_mm: 500, y_mm: 250 });
    expect(before.aircraft["UAS-01"].position.x_mm).toBe(0);
    expect(after.aircraft["UAS-01"].position.x_mm).toBe(1_000);
    expect(rendered.aircraft["UAS-01"].mode).toBe("SEARCH");
    expect(rendered).not.toBe(after);
  });

  it("clamps animation time and uses the newer snapshot for unmatched state", () => {
    const before = snapshotAt(100, 0, 0);
    const after = snapshotAt(200, 1_000, 500);
    const early = interpolateSnapshot(before, after, -1);
    const late = interpolateSnapshot(before, after, 10_000);
    expect(early.aircraft["UAS-01"].position).toEqual({ x_mm: 0, y_mm: 0 });
    expect(late.aircraft["UAS-01"].position).toEqual({ x_mm: 1_000, y_mm: 500 });
  });
});
